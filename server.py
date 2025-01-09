import socket
import threading
import pickle
import sys
import time

from utils import save_grid_to_image

ROOM_COUNT = 2           # Количество комнат
GRID_WIDTH = 16          # Ширина поля
GRID_HEIGHT = 16         # Высота поля
ROUND_TIME = 120          # Длительность раунда (секунды)

def create_empty_grid(width, height, default_color='#FFFFFF'):
    return [[default_color for _ in range(width)] for _ in range(height)]

rooms = {}
for i in range(1, ROOM_COUNT + 1):
    rooms[i] = {
        'grid': create_empty_grid(GRID_WIDTH, GRID_HEIGHT),
        'players': {},
        'round_active': False,
        'round_start_time': None,
        'room_lock': threading.Lock(),
    }

def broadcast_update(room_id):
    with rooms[room_id]['room_lock']:
        update_msg = {
            'type': 'update_state',
            'data': {
                'grid': rooms[room_id]['grid'],
                'players': list(rooms[room_id]['players'].keys()),
                'round_active': rooms[room_id]['round_active'],
            }
        }
        data = pickle.dumps(update_msg)
        for pinfo in rooms[room_id]['players'].values():
            try:
                pinfo['conn'].sendall(data)
            except:
                pass

def broadcast_chat(room_id, from_user, text):
    chat_msg = {
        'type': 'chat_broadcast',
        'data': {
            'from_user': from_user,
            'text': text
        }
    }
    data = pickle.dumps(chat_msg)
    with rooms[room_id]['room_lock']:
        for pinfo in rooms[room_id]['players'].values():
            try:
                pinfo['conn'].sendall(data)
            except:
                pass

def round_timer_thread(room_id):
    time.sleep(ROUND_TIME)

    with rooms[room_id]['room_lock']:
        if not rooms[room_id]['round_active']:
            return
        rooms[room_id]['round_active'] = False

    over_msg = {
        'type': 'round_over',
        'data': {
            'msg': f"Раунд в комнате {room_id} завершён!"
        }
    }
    over_data = pickle.dumps(over_msg)
    with rooms[room_id]['room_lock']:
        for pinfo in rooms[room_id]['players'].values():
            try:
                pinfo['conn'].sendall(over_data)
            except:
                pass
    
    filename = f"room_{room_id}_final.png"
    save_grid_to_image(rooms[room_id]['grid'], filename)
    print(f"[INFO] Room {room_id}: round finished, image saved to {filename}")

def client_handler(conn, addr):
    current_room_id = None
    username = None
    current_color = '#000000'

    print(f"[INFO] New client from {addr}")

    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break
            msg = pickle.loads(data)
            msg_type = msg.get('type')
            msg_data = msg.get('data', {})

            if msg_type == 'join':
                username = msg_data.get('username', 'Unknown')
                room_id = msg_data.get('room_id', 1)

                if room_id < 1 or room_id > ROOM_COUNT:
                    err_resp = {'type': 'error', 'data': 'Invalid room ID'}
                    conn.sendall(pickle.dumps(err_resp))
                    continue

                with rooms[room_id]['room_lock']:
                    rooms[room_id]['players'][username] = {
                        'conn': conn,
                        'color': current_color
                    }
                    if not rooms[room_id]['round_active']:
                        rooms[room_id]['round_active'] = True
                        rooms[room_id]['round_start_time'] = time.time()
                        t = threading.Thread(target=round_timer_thread, args=(room_id,), daemon=True)
                        t.start()

                current_room_id = room_id
                broadcast_update(room_id)
                broadcast_chat(room_id, "SERVER", f"{username} зашёл в комнату {room_id}.")

            elif msg_type == 'color':
                new_color = msg_data.get('color', '#000000')
                current_color = new_color
                with rooms[current_room_id]['room_lock']:
                    if username in rooms[current_room_id]['players']:
                        rooms[current_room_id]['players'][username]['color'] = current_color

            elif msg_type == 'draw':
                with rooms[current_room_id]['room_lock']:
                    if not rooms[current_room_id]['round_active']:
                        continue
                    x = msg_data.get('x')
                    y = msg_data.get('y')
                    color = msg_data.get('color', '#000000')

                    if 0 <= x < GRID_WIDTH and 0 <= y < GRID_HEIGHT:
                        rooms[current_room_id]['grid'][y][x] = color

                broadcast_update(current_room_id)

            elif msg_type == 'save':
                filename = f"room_{current_room_id}.png"
                with rooms[current_room_id]['room_lock']:
                    save_grid_to_image(rooms[current_room_id]['grid'], filename)
                resp = {'type': 'save_ok', 'data': filename}
                conn.sendall(pickle.dumps(resp))

            elif msg_type == 'chat':
                text = msg_data.get('text', '')
                broadcast_chat(current_room_id, username, text)

            elif msg_type == 'quit':
                break

            else:
                print(f"[WARN] Unknown message type: {msg_type}")

    except ConnectionResetError:
        pass
    except Exception as e:
        print(f"[ERROR] client_handler exception: {e}")

    finally:
        if current_room_id and username:
            with rooms[current_room_id]['room_lock']:
                if username in rooms[current_room_id]['players']:
                    del rooms[current_room_id]['players'][username]
            broadcast_chat(current_room_id, "SERVER", f"{username} вышел из комнаты.")
            broadcast_update(current_room_id)

        conn.close()
        print(f"[INFO] Connection closed: {addr}")

def main():
    HOST = '0.0.0.0'
    PORT = 777

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_socket.bind((HOST, PORT))
    except OSError as e:
        print(f"[ERROR] Bind failed: {e}")
        sys.exit(1)

    server_socket.listen(5)
    print(f"[INFO] Server started on {HOST}:{PORT}")

    try:
        while True:
            conn, addr = server_socket.accept()
            t = threading.Thread(target=client_handler, args=(conn, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        print("[INFO] Server shutting down by keyboard interrupt.")
    finally:
        server_socket.close()

if __name__ == '__main__':
    main()