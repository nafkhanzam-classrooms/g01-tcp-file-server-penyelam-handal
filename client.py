import socket
import os

HOST        = '127.0.0.1'
PORT        = 15579
BUFFER_SIZE = 4096


def strip_wrapping_quotes(text):
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'", '`'):
        return text[1:-1]
    return text

def send_line(sock, text):
    sock.sendall(f'{text}\n'.encode())


def recv_line(sock, buffer):
    while b'\n' not in buffer:
        data = sock.recv(BUFFER_SIZE)
        if not data:
            return None, buffer
        buffer += data

    raw_line, _, buffer = buffer.partition(b'\n')
    return raw_line.decode().strip(), buffer


def recv_exact(sock, size, buffer):
    chunks = []

    if buffer:
        take = min(len(buffer), size)
        chunks.append(buffer[:take])
        buffer = buffer[take:]
        size -= take

    while size > 0:
        data = sock.recv(min(BUFFER_SIZE, size))
        if not data:
            break
        chunks.append(data)
        size -= len(data)

    return b''.join(chunks), buffer


def list_files(sock, buffer):
    send_line(sock, '/list')
    response, buffer = recv_line(sock, buffer)
    if response is None:
        print('Disconnected from server.')
        return buffer

    if response.startswith('LIST '):
        try:
            payload_size = int(response.split(' ', 1)[1])
        except ValueError:
            print('Invalid response from server.')
            return buffer

        payload, buffer = recv_exact(sock, payload_size, buffer)
        response = payload.decode(errors='replace')

    print('Files in server:')
    print(response)
    return buffer


def upload(sock, filepath, buffer):
    if not os.path.exists(filepath):
        print('File does not exist.')
        return buffer
    
    file_size = os.path.getsize(filepath)
    filename = os.path.basename(filepath)

    send_line(sock, f'/upload {filename}')

    status, buffer = recv_line(sock, buffer)
    if status != 'READY_FOR_SIZE':
        print(status or 'Server did not respond for upload.')
        return buffer

    send_line(sock, str(file_size))

    ack, buffer = recv_line(sock, buffer)
    if ack != 'READY_FOR_UPLOAD':
        print(ack or 'Server is not ready for upload.')
        return buffer
    
    print(f'Uploading {filepath} ({file_size} bytes)...')

    with open(filepath, 'rb') as f:
        while True:
            chunk = f.read(BUFFER_SIZE)
            if not chunk:
                break
            sock.sendall(chunk)

    status, buffer = recv_line(sock, buffer)
    if status is None:
        print('Disconnected from server after upload.')
        return buffer

    print(status)
    return buffer


def download(sock, filename, save_path, buffer):
    send_line(sock, f'/download {filename}')
    response, buffer = recv_line(sock, buffer)
    if response is None:
        print('Disconnected from server.')
        return buffer

    if response.startswith('ERR'):
        print(response)
        return buffer

    if not response.startswith('SIZE '):
        print('Invalid response from server.')
        return buffer
    
    try:
        file_size = int(response.split(' ', 1)[1])
    except ValueError:
        print('Invalid response from server.')
        return buffer

    send_line(sock, 'READY_FOR_DOWNLOAD')
    
    print(f'Downloading {filename} ({file_size} bytes)...')

    data, buffer = recv_exact(sock, file_size, buffer)
    received = len(data)

    if os.path.isdir(save_path) or save_path in ('.', '..') or save_path.endswith(os.sep):
        destination_path = os.path.join(save_path, os.path.basename(filename))
    else:
        destination_path = save_path

    parent_dir = os.path.dirname(destination_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    with open(destination_path, 'wb') as f:
        f.write(data)

    if received == file_size:
        print(f'File downloaded successfully: {destination_path} ({received} bytes)')
    else:
        print(f'File download incomplete: expected {file_size} bytes, received {received} bytes')

    return buffer

def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((HOST, PORT))
        print(f'Connected to server at {HOST}:{PORT}')

        buffer = b''
        welcome, buffer = recv_line(sock, buffer)
        if welcome:
            print(welcome)
            print()

        while True:
            command = input('\n> ').strip()
            if command == '/exit':
                break
            elif command == '/list':
                buffer = list_files(sock, buffer)
            elif command.startswith('/upload '):
                _, filepath = command.split(' ', 1)
                filepath = strip_wrapping_quotes(filepath.strip())
                buffer = upload(sock, filepath, buffer)
            elif command.startswith('/download '):
                remainder = command[len('/download '):].strip()
                if ' ' not in remainder:
                    print('Invalid download command. Usage: /download <filename> <save_path>')
                    continue
                filename, save_path = remainder.rsplit(' ', 1)
                filename = strip_wrapping_quotes(filename.strip())
                save_path = strip_wrapping_quotes(save_path.strip())
                if not filename or not save_path:
                    print('Invalid download command. Usage: /download <filename> <save_path>')
                    continue
                buffer = download(sock, filename, save_path, buffer)
            else:
                print('Unknown command. Use /list, /upload, /download, or /exit.')

if __name__ == '__main__':
    main()