import socket
import os

HOST        = '0.0.0.0'
PORT        = 15579
SERVER_DIR  = './server_files'
BUFFER_SIZE = 4096


def send_line(conn, text):
    conn.sendall(f'{text}\n'.encode())


def recv_line(conn, buffer):
    while b'\n' not in buffer:
        data = conn.recv(BUFFER_SIZE)
        if not data:
            return None, buffer
        buffer += data

    raw_line, _, buffer = buffer.partition(b'\n')
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

    return b''.join(chunks), buffer


def sanitize_filename(filename):
    safe_name = os.path.basename(filename)
    if safe_name != filename or safe_name in ('', '.', '..'):
        return None
    return safe_name

def check_dir():
    if not os.path.exists(SERVER_DIR):
        os.makedirs(SERVER_DIR)

def handle_list(conn):
    files = os.listdir(SERVER_DIR)
    if files:
        response = '\n'.join(files)
    else:
        response = 'There is no file in server.'
    payload = response.encode()
    send_line(conn, f'LIST {len(payload)}')
    conn.sendall(payload)

def handle_upload(conn, filename, buffer):
    send_line(conn, 'READY_FOR_SIZE')

    size_data, buffer = recv_line(conn, buffer)
    if size_data is None:
        send_line(conn, 'ERR: Connection closed before file size was received.')
        return buffer

    try:
        file_size = int(size_data)
        if file_size < 0:
            raise ValueError
    except ValueError:
        send_line(conn, 'ERR: Invalid file size.')
        return buffer
    
    send_line(conn, 'READY_FOR_UPLOAD')

    filepath = os.path.join(SERVER_DIR, filename)
    content, buffer = recv_exact(conn, file_size, buffer)
    received = len(content)

    if received == file_size:
        with open(filepath, 'wb') as f:
            f.write(content)
        send_line(conn, f'OK: uploaded {filename} ({received} bytes)')
        print(f'File Uploaded: {filename} ({received} bytes) from {conn.getpeername()}')
    else:
        send_line(conn, f'ERR: Incomplete upload for {filename}: expected {file_size} bytes, received {received} bytes.')
        print(f'Upload Incomplete: {filename} (expected {file_size} bytes, received {received} bytes) from {conn.getpeername()}')

    return buffer

def handle_download(conn, filename, buffer):
    filepath = os.path.join(SERVER_DIR, filename)

    if not os.path.isfile(filepath):
        send_line(conn, 'ERR: File not found.')
        return buffer
    
    file_size = os.path.getsize(filepath)
    send_line(conn, f'SIZE {file_size}')

    ack, buffer = recv_line(conn, buffer)
    if ack != 'READY_FOR_DOWNLOAD':
        send_line(conn, 'ERR: Download was not acknowledged by client.')
        return buffer
    
    with open(filepath, 'rb') as f:
        while True:
            chunk = f.read(BUFFER_SIZE)
            if not chunk:
                break
            conn.sendall(chunk)
    
    print(f'File Downloaded: {filename} ({file_size} bytes) to {conn.getpeername()}')
    return buffer

def handle_client(conn, addr):
    print(f'Client connected: {addr}')
    send_line(conn, 'Welcome to File Server, available commands: /list, /upload <filename>, /download <filename> <save_path>')
    buffer = b''

    try:
        while True:
            message, buffer = recv_line(conn, buffer)
            if message is None:
                print(f'Client disconnected: {addr}')
                break

            if not message:
                continue

            print(f'Received from {addr}: {message}')

            if message == '/list':
                handle_list(conn)

            elif message.startswith('/upload '):
                print(f'Upload request from {addr}: {message}')
                parts = message.split(' ', 1)
                if len(parts) != 2 or not parts[1].strip():
                    send_line(conn, 'ERR: Invalid upload command. Usage: /upload <filename>')
                    continue
                raw_filename = parts[1].strip()
                filename = sanitize_filename(raw_filename)
                if not filename:
                    send_line(conn, 'ERR: Invalid filename.')
                    continue
                buffer = handle_upload(conn, filename, buffer)


            elif message.startswith('/download '):
                print(f'Download request from {addr}: {message}')
                parts = message.split(' ', 1)
                if len(parts) != 2 or not parts[1].strip():
                    send_line(conn, 'ERR: Invalid download command. Usage: /download <filename>')
                    continue
                raw_filename = parts[1].strip()
                filename = sanitize_filename(raw_filename)
                if not filename:
                    send_line(conn, 'ERR: Invalid filename.')
                    continue
                buffer = handle_download(conn, filename, buffer)

            else:
                send_line(conn, 'ERR: Unknown command. Please check your input.')

    except Exception as e:
        print(f'Error handling client {addr}: {e}')
    finally:
        conn.close()

def main():
    check_dir()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(1)

    print(f'Server is listening on {HOST}:{PORT}...')
    print(f'Waiting for clients to connect...\n')

    try: 
        while True:
            conn, addr = server.accept()
            handle_client(conn, addr)
            print(f'Connection closed: {addr}\n')
    
    except KeyboardInterrupt:
        print('Shutting down server...')
    finally:
        server.close()
    
if __name__ == '__main__':
    main()