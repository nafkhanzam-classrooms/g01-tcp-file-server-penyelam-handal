import os
import socket
import threading
import math

HOST = "0.0.0.0"
PORT = 15579
SERVER_DIR = "./server_files"
BUFFER_SIZE = 4096
CLIENTS = set()
CLIENTS_LOCK = threading.Lock()


def format_size_notation(file_size):
	units = ["B", "KB", "MB", "GB", "TB"]
	value = float(file_size) if file_size > 0 else 0.0
	unit_index = 0

	while value >= 1000 and unit_index < len(units) - 1:
		value /= 1024
		unit_index += 1

	value = math.ceil(value * 100) / 100

	if value >= 1000 and unit_index < len(units) - 1:
		value = math.ceil((value / 1024) * 100) / 100
		unit_index += 1

	return f"{value:.2f} {units[unit_index]}"


def send_line(conn, text):
	conn.sendall(f"{text}\n".encode())


def add_client(conn):
	with CLIENTS_LOCK:
		CLIENTS.add(conn)


def remove_client(conn):
	with CLIENTS_LOCK:
		CLIENTS.discard(conn)


def broadcast_to_others(sender_conn, text):
	message = f"BROADCAST {text}"
	failed = []

	with CLIENTS_LOCK:
		targets = [conn for conn in CLIENTS if conn is not sender_conn]

	for conn in targets:
		try:
			send_line(conn, message)
		except OSError:
			failed.append(conn)

	for conn in failed:
		remove_client(conn)

	return len(targets) - len(failed)


def recv_line(conn, buffer):
	while b"\n" not in buffer:
		data = conn.recv(BUFFER_SIZE)
		if not data:
			return None, buffer
		buffer += data

	raw_line, _, buffer = buffer.partition(b"\n")
	return raw_line.decode().strip(), buffer


def recv_exact(conn, size, buffer):
	chunks = []

	if buffer:
		take = min(len(buffer), size)
		chunks.append(buffer[:take])
		buffer = buffer[take:]
		size -= take

	while size > 0:
		data = conn.recv(min(BUFFER_SIZE, size))
		if not data:
			break
		chunks.append(data)
		size -= len(data)

	return b"".join(chunks), buffer


def sanitize_filename(filename):
	safe_name = os.path.basename(filename)
	if safe_name != filename or safe_name in ("", ".", ".."):
		return None
	return safe_name


def check_dir():
	if not os.path.exists(SERVER_DIR):
		os.makedirs(SERVER_DIR)


def handle_list(conn):
	files = []
	for name in os.listdir(SERVER_DIR):
		path = os.path.join(SERVER_DIR, name)
		if os.path.isfile(path):
			size = os.path.getsize(path)
			files.append((format_size_notation(size), name))
	if files:
		width = max(len(size_text) for size_text, _ in files)
		response = "\n".join(
			f"{size_text:<{width}}    {name}" for size_text, name in files
		)
	else:
		response = "There is no file in server."
	payload = response.encode()
	send_line(conn, f"LIST {len(payload)}")
	conn.sendall(payload)


def handle_upload(conn, filename, buffer):
	send_line(conn, "READY_FOR_SIZE")

	size_data, buffer = recv_line(conn, buffer)
	if size_data is None:
		send_line(conn, "ERR: Connection closed before file size was received.")
		return buffer

	try:
		file_size = int(size_data)
		if file_size < 0:
			raise ValueError
	except ValueError:
		send_line(conn, "ERR: Invalid file size.")
		return buffer

	send_line(conn, "READY_FOR_UPLOAD")

	filepath = os.path.join(SERVER_DIR, filename)
	content, buffer = recv_exact(conn, file_size, buffer)
	received = len(content)

	if received == file_size:
		with open(filepath, "wb") as f:
			f.write(content)
		send_line(conn, f"OK: uploaded {filename} ({received} bytes)")
		print(f"File Uploaded: {filename} ({received} bytes) from {conn.getpeername()}")
	else:
		send_line(
			conn,
			f"ERR: Incomplete upload for {filename}: expected {file_size} bytes, received {received} bytes.",
		)
		print(
			f"Upload Incomplete: {filename} (expected {file_size} bytes, received {received} bytes) from {conn.getpeername()}"
		)

	return buffer


def handle_download(conn, filename, buffer):
	filepath = os.path.join(SERVER_DIR, filename)

	if not os.path.isfile(filepath):
		send_line(conn, "ERR: File not found.")
		return buffer

	file_size = os.path.getsize(filepath)
	send_line(conn, f"SIZE {file_size}")

	ack, buffer = recv_line(conn, buffer)
	if ack != "READY_FOR_DOWNLOAD":
		send_line(conn, "ERR: Download was not acknowledged by client.")
		return buffer

	with open(filepath, "rb") as f:
		while True:
			chunk = f.read(BUFFER_SIZE)
			if not chunk:
				break
			conn.sendall(chunk)

	print(f"File Downloaded: {filename} ({file_size} bytes) to {conn.getpeername()}")
	return buffer


def handle_client(conn, addr):
	print(f"Client connected: {addr}")
	send_line(
		conn,
		"Welcome to File Server, available commands: /list, /upload <filename>, /download <filename> <save_path>, /broadcast <message>",
	)
	buffer = b""

	try:
		while True:
			message, buffer = recv_line(conn, buffer)
			if message is None:
				print(f"Client disconnected: {addr}")
				break

			if not message:
				continue

			print(f"Received from {addr}: {message}")

			if message == "/list":
				handle_list(conn)

			elif message.startswith("/upload "):
				print(f"Upload request from {addr}: {message}")
				parts = message.split(" ", 1)
				if len(parts) != 2 or not parts[1].strip():
					send_line(conn, "ERR: Invalid upload command. Usage: /upload <filename>")
					continue

				filename = sanitize_filename(parts[1].strip())
				if not filename:
					send_line(conn, "ERR: Invalid filename.")
					continue
				buffer = handle_upload(conn, filename, buffer)

			elif message.startswith("/download "):
				print(f"Download request from {addr}: {message}")
				parts = message.split(" ", 1)
				if len(parts) != 2 or not parts[1].strip():
					send_line(conn, "ERR: Invalid download command. Usage: /download <filename>")
					continue

				filename = sanitize_filename(parts[1].strip())
				if not filename:
					send_line(conn, "ERR: Invalid filename.")
					continue
				buffer = handle_download(conn, filename, buffer)

			elif message.startswith("/broadcast "):
				broadcast_message = message.split(" ", 1)[1].strip()
				if not broadcast_message:
					send_line(conn, "ERR: Invalid broadcast command. Usage: /broadcast <message>")
					continue

				sent_count = broadcast_to_others(conn, f"from {addr}: {broadcast_message}")
				send_line(conn, f"OK: broadcast sent to {sent_count} client(s).")

			else:
				send_line(conn, "ERR: Unknown command. Please check your input.")

	except Exception as exc:
		print(f"Error handling client {addr}: {exc}")
	finally:
		remove_client(conn)
		conn.close()


def main():
	check_dir()

	server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	server.bind((HOST, PORT))
	server.listen(128)
	server.settimeout(1.0)

	print(f"Threaded server is listening on {HOST}:{PORT}...")
	print("Waiting for clients to connect...\n")

	workers = []
	stop_event = threading.Event()

	try:
		while not stop_event.is_set():
			try:
				conn, addr = server.accept()
			except socket.timeout:
				continue

			worker = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
			add_client(conn)
			worker.start()
			workers.append(worker)

			# Remove finished threads to keep list small.
			workers = [thread for thread in workers if thread.is_alive()]

	except KeyboardInterrupt:
		print("Shutting down threaded server...")
		stop_event.set()
	finally:
		server.close()
		for worker in workers:
			worker.join(timeout=1.0)


if __name__ == "__main__":
	main()
