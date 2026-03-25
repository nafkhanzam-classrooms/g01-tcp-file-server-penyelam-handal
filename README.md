[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/mRmkZGKe)
# Network Programming - Assignment G01

## Anggota Kelompok
| Nama                        | NRP        | Kelas     |
| ---                         | ---        | ----------|
| Jalu Cahyo Senodiputro      | 5025241155 |    C      |
| Erlangga Rizqi Dwi Raswanto | 5025241179 |    C      |

## Link Youtube (Unlisted)
Link ditaruh di bawah ini
```

```

## Penjelasan Program

### 1. client.py
Program client digunakan untuk terhubung ke server dan mengirim perintah dari terminal.

Fitur utama:
- `/list`: meminta daftar file yang tersedia di folder server.
- `/upload <filepath>`: mengunggah file lokal ke server.
- `/download <filename> <save_path>`: mengunduh file dari server ke path lokal.
- `/exit`: keluar dari client.

Alur protokol client:
- Client *connect* ke server.
- User menuliskan command di client yang kemudian dikirimkan ke server.
- Client menerima dan menampilkan *response* dari server.

### 2. server-sync.py
Implementasi pada server sinkron dibagi menjadi beberapa fungsi inti:

- `send_line(conn, text)`: mengirim 1 baris pesan teks dengan akhiran newline.
- `recv_line(conn, buffer)`: membaca data dari socket sampai menemukan newline, lalu mengembalikan 1 baris command + sisa buffer.
- `recv_exact(conn, size, buffer)`: membaca tepat sejumlah byte (dipakai untuk isi file saat upload/download).
- `sanitize_filename(filename)`: validasi nama file agar hanya nama file biasa
- `handle_list(conn)`: membaca isi folder `server_files`, lalu kirim `LIST <size>` diikuti payload daftar file.
- `handle_upload(conn, filename, buffer)`: handshake upload (`READY_FOR_SIZE` -> terima size -> `READY_FOR_UPLOAD` -> terima byte file -> simpan ke disk).
- `handle_download(conn, filename, buffer)`: handshake download (kirim `SIZE` -> tunggu `READY_FOR_DOWNLOAD` -> kirim isi file).
- `handle_client(conn, addr)`: loop utama parsing command (`/list`, `/upload`, `/download`) dan pilih handler yg sesuai.
- `main()`: setup socket server (`SO_REUSEADDR`, `bind`, `listen`), menerima koneksi, lalu memproses client satu per satu.

### 3. server-thread.py
Struktur fungsinya sama dengan *server-sync* (`send_line`, `recv_line`, `recv_exact`, `handle_list`, `handle_upload`, `handle_download`, `handle_client`), tetapi pada `main()` implementasinya berbeda:

- Server menerima koneksi dari `accept()`.
- Setiap koneksi dijalankan di thread baru dengan `threading.Thread(target=handle_client, ...)`.
- Daftar worker thread disimpan dan dibersihkan dari thread yang sudah selesai (`is_alive()`).
- Saat `KeyboardInterrupt`, server ditutup lalu thread-thread yang masih aktif di-*join* dengan timeout.

Dengan begitu, alur command per client tetap sama seperti sync, tetapi diproses di thread terpisah.

### 4. server-select.py
Server ini memakai event loop non-blocking berbasis `select.select()`.

Implementasi utamanya:
- Socket server di-set non-blocking (`setblocking(False)`).
- Data client disimpan dalam dictionary `clients`, berisi:
	- `in_buffer` dan `out_buffer`
	- `state` (`COMMAND`, `WAIT_UPLOAD_SIZE`, `WAIT_UPLOAD_CONTENT`, `WAIT_DOWNLOAD_ACK`)
	- metadata upload (`pending_filename`, `upload_size`, `upload_received`, `upload_file`)
- `queue_line()` dan `queue_bytes()` dipakai untuk menaruh data respons ke `out_buffer`.
- `process_client_buffer(client)` menjalankan state machine protokol:
	- state `COMMAND`: parse command baris-per-baris
	- state upload: validasi size lalu tulis byte file bertahap
	- state download: tunggu ACK lalu antrekan byte file ke `out_buffer`
- Di loop `main()`, `select.select()` menghasilkan:
	- `readable`: terima koneksi baru atau baca data client
	- `writable`: kirim data yang menunggu di `out_buffer`
	- `exceptional`: tutup koneksi bermasalah lewat `close_client()`

### 5. server-poll.py
Implementasi server ini hampir sama dengan `server-select.py`, tetapi event multiplexer diganti ke `select.poll()`.

Detail implementasi:
- Server dan client socket diregister ke objek `poller`.
- `fd_map` dipakai untuk memetakan file descriptor ke objek socket.
- `update_interest(poller, sock, client)` mengatur event yang dipantau:
	- selalu `POLLIN`
	- tambah `POLLOUT` jika `out_buffer` tidak kosong
- Di loop `main()`, `poller.poll()` membaca event lalu diproses:
	- event server: accept banyak koneksi selama masih tersedia
	- `POLLIN`: baca data dan proses state machine
	- `POLLOUT`: flush data dari `out_buffer`
	- `POLLHUP/POLLERR/POLLNVAL`: koneksi ditutup aman

State machine command upload/download/list pada `server-poll.py` sama dengan versi select, hanya mekanisme event-nya yang berbeda (`poll` alih-alih `select`).


### Command Protokol
1. List file
	- Client: `/list`
	- Server: `LIST <panjang_payload>` lalu isi daftar file.

2. Upload file
	- Client: `/upload <filename>`
	- Server: `READY_FOR_SIZE`
	- Client: `<file_size>`
	- Server: `READY_FOR_UPLOAD`
	- Client: kirim byte file
	- Server: balasan `OK` atau `ERR`

3. Download file
	- Client: `/download <filename>`
	- Server: `SIZE <file_size>` atau `ERR`
	- Client: `READY_FOR_DOWNLOAD`
	- Server: kirim byte file

### Keamanan dan Validasi Dasar
- Nama file disanitasi agar tidak bisa mengakses path di luar folder server.
- Ukuran file divalidasi saat upload.
- Jika transfer tidak lengkap, server mengirim pesan error.

## Screenshot Hasil

### server-sync.py
![server-sync](assets/server-sync.png)

### server-poll.py
![server-poll](assets/server-poll.png)


### server-select.py
![server-select](assets/server-select.png)


### server-thread.py
![server-thread](assets/server-thread.png)

