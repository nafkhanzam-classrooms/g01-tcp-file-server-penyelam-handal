import os
import select
import socket

HOST = "0.0.0.0"
PORT = 15579
SERVER_DIR = "./server_files"
BUFFER_SIZE = 4096


def check_dir():
	if not os.path.exists(SERVER_DIR):
		os.makedirs(SERVER_DIR)


def sanitize_filename(filename):
	safe_name = os.path.basename(filename)
	if safe_name != filename or safe_name in ("", ".", ".."):
		return None
	return safe_name


def queue_line(client, text):
	queue_bytes(client, f"{text}\n".encode())


def queue_bytes(client, data):
	client["out_buffer"] += data


def get_peer_name(sock):
	try:
		return sock.getpeername()
	except OSError:
		return ("unknown", 0)


def close_client(sock, clients, read_sockets):
	client = clients.pop(sock, None)
	if client is None:
		return

	if sock in read_sockets:
		read_sockets.remove(sock)

	upload_file = client.get("upload_file")
	if upload_file is not None:
		upload_file.close()

	print(f"Client disconnected: {client['addr']}")
	sock.close()


def handle_command_line(client, line):
	addr = client["addr"]

	if line == "/list":
		files = os.listdir(SERVER_DIR)
		response = "\n".join(files) if files else "There is no file in server."
		payload = response.encode()
		queue_line(client, f"LIST {len(payload)}")
		queue_bytes(client, payload)
		return

	if line.startswith("/upload "):
		parts = line.split(" ", 1)
		if len(parts) != 2 or not parts[1].strip():
			queue_line(client, "ERR: Invalid upload command. Usage: /upload <filename>")
			return

		filename = sanitize_filename(parts[1].strip())
		if not filename:
			queue_line(client, "ERR: Invalid filename.")
			return

		client["state"] = "WAIT_UPLOAD_SIZE"
		client["pending_filename"] = filename
		queue_line(client, "READY_FOR_SIZE")
		print(f"Upload request from {addr}: {line}")
		return

	if line.startswith("/download "):
		parts = line.split(" ", 1)
		if len(parts) != 2 or not parts[1].strip():
			queue_line(client, "ERR: Invalid download command. Usage: /download <filename>")
			return

		filename = sanitize_filename(parts[1].strip())
		if not filename:
			queue_line(client, "ERR: Invalid filename.")
			return

		filepath = os.path.join(SERVER_DIR, filename)
		if not os.path.isfile(filepath):
			queue_line(client, "ERR: File not found.")
			return

		file_size = os.path.getsize(filepath)
		client["state"] = "WAIT_DOWNLOAD_ACK"
		client["pending_filename"] = filename
		queue_line(client, f"SIZE {file_size}")
		print(f"Download request from {addr}: {line}")
		return

	queue_line(client, "ERR: Unknown command. Please check your input.")


def process_client_buffer(client):
	addr = client["addr"]

	while True:
		if client["state"] == "COMMAND":
			if b"\n" not in client["in_buffer"]:
				break

			raw_line, _, remaining = client["in_buffer"].partition(b"\n")
			client["in_buffer"] = remaining
			line = raw_line.decode(errors="replace").strip()

			if not line:
				continue

			print(f"Received from {addr}: {line}")
			handle_command_line(client, line)
			continue

		if client["state"] == "WAIT_UPLOAD_SIZE":
			if b"\n" not in client["in_buffer"]:
				break

			raw_line, _, remaining = client["in_buffer"].partition(b"\n")
			client["in_buffer"] = remaining
			size_line = raw_line.decode(errors="replace").strip()

			try:
				upload_size = int(size_line)
				if upload_size < 0:
					raise ValueError
			except ValueError:
				queue_line(client, "ERR: Invalid file size.")
				client["state"] = "COMMAND"
				client["pending_filename"] = None
				continue

			filename = client["pending_filename"]
			filepath = os.path.join(SERVER_DIR, filename)
			client["upload_file"] = open(filepath, "wb")
			client["upload_size"] = upload_size
			client["upload_received"] = 0
			client["state"] = "WAIT_UPLOAD_CONTENT"
			queue_line(client, "READY_FOR_UPLOAD")
			continue

		if client["state"] == "WAIT_UPLOAD_CONTENT":
			remaining = client["upload_size"] - client["upload_received"]
			if remaining <= 0:
				client["upload_file"].close()
				client["upload_file"] = None
				filename = client["pending_filename"]
				queue_line(client, f"OK: uploaded {filename} ({client['upload_size']} bytes)")
				print(f"File Uploaded: {filename} ({client['upload_size']} bytes) from {addr}")
				client["state"] = "COMMAND"
				client["pending_filename"] = None
				continue

			if not client["in_buffer"]:
				break

			chunk = client["in_buffer"][:remaining]
			client["in_buffer"] = client["in_buffer"][len(chunk):]
			client["upload_file"].write(chunk)
			client["upload_received"] += len(chunk)
			continue

		if client["state"] == "WAIT_DOWNLOAD_ACK":
			if b"\n" not in client["in_buffer"]:
				break

			raw_line, _, remaining = client["in_buffer"].partition(b"\n")
			client["in_buffer"] = remaining
			ack = raw_line.decode(errors="replace").strip()
			filename = client["pending_filename"]

			if ack != "READY_FOR_DOWNLOAD":
				queue_line(client, "ERR: Download was not acknowledged by client.")
				client["state"] = "COMMAND"
				client["pending_filename"] = None
				continue

			filepath = os.path.join(SERVER_DIR, filename)
			with open(filepath, "rb") as f:
				while True:
					chunk = f.read(BUFFER_SIZE)
					if not chunk:
						break
					queue_bytes(client, chunk)

			print(
				f"File Downloaded: {filename} ({os.path.getsize(filepath)} bytes) to {get_peer_name(client['sock'])}"
			)
			client["state"] = "COMMAND"
			client["pending_filename"] = None
			continue

		break


def flush_outgoing(sock, client):
	if not client["out_buffer"]:
		return

	try:
		sent = sock.send(client["out_buffer"])
	except BlockingIOError:
		return

	if sent > 0:
		client["out_buffer"] = client["out_buffer"][sent:]


def main():
	check_dir()

	server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	server.bind((HOST, PORT))
	server.listen(128)
	server.setblocking(False)

	clients = {}
	read_sockets = [server]

	print(f"Select server is listening on {HOST}:{PORT}...")
	print("Waiting for clients to connect...\n")

	try:
		while True:
			write_sockets = [
				sock for sock, client in clients.items() if client["out_buffer"]
			]
			readable, writable, exceptional = select.select(
				read_sockets, write_sockets, read_sockets, 1.0
			)

			for sock in readable:
				if sock is server:
					conn, addr = server.accept()
					conn.setblocking(False)
					read_sockets.append(conn)
					clients[conn] = {
						"sock": conn,
						"addr": addr,
						"in_buffer": b"",
						"out_buffer": b"",
						"state": "COMMAND",
						"pending_filename": None,
						"upload_file": None,
						"upload_size": 0,
						"upload_received": 0,
					}
					queue_line(
						clients[conn],
						"Welcome to File Server, available commands: /list, /upload <filename>, /download <filename> <save_path>",
					)
					print(f"Client connected: {addr}")
					continue

				try:
					data = sock.recv(BUFFER_SIZE)
				except BlockingIOError:
					continue
				except ConnectionResetError:
					close_client(sock, clients, read_sockets)
					continue

				if not data:
					close_client(sock, clients, read_sockets)
					continue

				client = clients[sock]
				client["in_buffer"] += data
				process_client_buffer(client)

			for sock in writable:
				client = clients.get(sock)
				if client is None:
					continue
				flush_outgoing(sock, client)

			for sock in exceptional:
				if sock is server:
					continue
				close_client(sock, clients, read_sockets)

	except KeyboardInterrupt:
		print("Shutting down select server...")
	finally:
		for sock in list(clients.keys()):
			close_client(sock, clients, read_sockets)
		server.close()


if __name__ == "__main__":
	main()
