import socket
import os

HOST        = '0.0.0.0'
PORT        = 15579
SERVER_DIR  = './server_files'
BUFFER_SIZE = 4096

def check_dir():
    if not os.path.exists(SERVER_DIR):
        os.makedirs(SERVER_DIR)

def handle_list(conn):
    files = os.listdir(SERVER_DIR)
    if files:
        response = '\n'.join(files)
    else:
        response = 'There is no file in server.'
    conn.sendall(response.encode())

def handle_upload(conn, filename):
    size_data = conn.recv(BUFFER_SIZE).decode().strip()
    try:
        file_size = int(size_data)
    except ValueError:
        conn.sendall('ERR: Invalid file size.'.encode())
        return
    
    conn.sendall('Ready to Upload'.encode())

    filepath = os.path.join(SERVER_DIR, filename)
    received = 0
    
    with open(filepath, 'wb') as f:
        while received < file_size:
            chunk = conn.recv(min(BUFFER_SIZE, file_size - received))
            if not chunk:
                break
            f.write(chunk)
            received += len(chunk)

    if received == file_size:
        conn.sendall(f'OK: uploaded {filename} ({received} bytes)'.encode())
        print(f'File Uploaded: {filename} ({received} bytes) from {conn.getpeername()}')
    else:
        conn.sendall(
            f'ERR: Incomplete upload for {filename}: expected {file_size} bytes, received {received} bytes.'.encode()
        )
        print(f'Upload Incomplete: {filename} (expected {file_size} bytes, received {received} bytes) from {conn.getpeername()}')

def handle_download(conn, filename):
    filepath = os.path.join(SERVER_DIR, filename)

    if not os.path.isfile(filepath):
        conn.sendall('ERR: File not found.'.encode())
        return
    
    file_size = os.path.getsize(filepath)
    conn.sendall(str(file_size).encode())

    ack = conn.recv(BUFFER_SIZE).decode()
    if ack != 'Ready to Download':
        return
    
    with open(filepath, 'rb') as f:
        while True:
            chunk = f.read(BUFFER_SIZE)
            if not chunk:
                break
            conn.sendall(chunk)
    
    print(f'File Downloaded: {filename} ({file_size} bytes) to {conn.getpeername()}')

def handle_client(conn, addr):
    print(f'Client connected: {addr}')
    conn.sendall('Welcome to File Server, available commands: /list, /upload <filename>, /download <filename>'.encode())

    try:
        while True:
            data = conn.recv(BUFFER_SIZE)
            if not data:
                print(f'Client disconnected: {addr}')
                break

            message = data.decode().strip()
            print(f'Received from {addr}: {message}')

            if message == '/list':
                handle_list(conn)

            elif message.startswith('/upload '):
                print(f'Upload request from {addr}: {message}')
                parts = message.split(' ', 1)
                if len(parts) != 2 or not parts[1].strip():
                    conn.sendall('ERR: Invalid upload command. Usage: /upload <filename>'.encode())
                    continue
                filename = parts[1].strip()
                handle_upload(conn, filename)


            elif message.startswith('/download '):
                print(f'Download request from {addr}: {message}')
                parts = message.split(' ', 1)
                if len(parts) != 2 or not parts[1].strip():
                    conn.sendall('ERR: Invalid download command. Usage: /download <filename>'.encode())
                    continue
                filename = parts[1].strip()
                handle_download(conn, filename)

            else:
                conn.sendall('ERR: Unknown command. Please check your input.'.encode())

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