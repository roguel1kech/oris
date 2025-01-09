import sys
import socket
import threading
import pickle

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QGridLayout, QPushButton,
    QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QMessageBox, QTextEdit,
    QColorDialog
)

class PixelBattleClient(QMainWindow):

    newServerMessage = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.sock = None
        self.recv_thread = None

        self.grid_width = 16
        self.grid_height = 16
        self.is_round_active = False
        self.current_color = '#FF0000'

        self.newServerMessage.connect(self.onServerMessageMainThread)

        container = QWidget()
        self.setCentralWidget(container)
        main_layout = QVBoxLayout(container)

        top_panel = QHBoxLayout()
        main_layout.addLayout(top_panel)

        top_panel.addWidget(QLabel("Username:"))
        self.username_edit = QLineEdit("Player1")
        top_panel.addWidget(self.username_edit)

        top_panel.addWidget(QLabel("Room:"))
        self.room_edit = QLineEdit("1")
        self.room_edit.setFixedWidth(40)
        top_panel.addWidget(self.room_edit)

        connect_btn = QPushButton("Connect")
        connect_btn.clicked.connect(self.on_connect_clicked)
        top_panel.addWidget(connect_btn)

        btn_panel = QHBoxLayout()
        main_layout.addLayout(btn_panel)

        self.color_btn = QPushButton("Choose Color")
        self.color_btn.setEnabled(False)
        self.color_btn.clicked.connect(self.choose_color)
        btn_panel.addWidget(self.color_btn)

        self.save_btn = QPushButton("Save Field")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.send_save)
        btn_panel.addWidget(self.save_btn)

        center_panel = QHBoxLayout()
        main_layout.addLayout(center_panel)

        chat_layout = QVBoxLayout()
        center_panel.addLayout(chat_layout, stretch=1)

        chat_label = QLabel("Чат:")
        chat_layout.addWidget(chat_label)

        self.chat_area = QTextEdit()
        self.chat_area.setReadOnly(True)
        chat_layout.addWidget(self.chat_area, stretch=1)

        chat_input_panel = QHBoxLayout()
        self.chat_input = QLineEdit()
        send_chat_btn = QPushButton("Отправить")
        send_chat_btn.clicked.connect(self.on_send_chat)
        chat_input_panel.addWidget(self.chat_input, stretch=1)
        chat_input_panel.addWidget(send_chat_btn)
        chat_layout.addLayout(chat_input_panel)

        self.field_widget = QWidget()
        self.field_layout = QGridLayout(self.field_widget)
        self.field_layout.setSpacing(1)
        center_panel.addWidget(self.field_widget, stretch=2)

        self.buttons = []
        for y in range(self.grid_height):
            row_btns = []
            for x in range(self.grid_width):
                btn = QPushButton("")
                btn.setFixedSize(24, 24)
                btn.setStyleSheet("background-color: #FFFFFF; border: 1px solid #CCC;")
                btn.clicked.connect(self.make_draw_callback(x, y))
                self.field_layout.addWidget(btn, y, x)
                row_btns.append(btn)
            self.buttons.append(row_btns)

        self.setWindowTitle("Pixel Battle (16x16)")
        self.resize(900, 600)

    def make_draw_callback(self, x, y):
        def callback():
            if self.sock and self.is_round_active:
                msg = {
                    'type': 'draw',
                    'data': {
                        'x': x,
                        'y': y,
                        'color': self.current_color
                    }
                }
                self.send_msg(msg)
        return callback

    def on_connect_clicked(self):
        if self.sock:
            QMessageBox.information(self, "Info", "Already connected!")
            return

        username = self.username_edit.text().strip()
        if not username:
            QMessageBox.warning(self, "Warning", "Username cannot be empty.")
            return

        room_str = self.room_edit.text().strip()
        try:
            room_id = int(room_str)
        except ValueError:
            QMessageBox.warning(self, "Warning", "Room must be integer.")
            return

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sock.connect(('127.0.0.1', 777))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to connect: {e}")
            self.sock = None
            return

        self.recv_thread = threading.Thread(target=self.listen_server, daemon=True)
        self.recv_thread.start()

        join_msg = {
            'type': 'join',
            'data': {
                'username': username,
                'room_id': room_id
            }
        }
        self.send_msg(join_msg)

        self.color_btn.setEnabled(True)
        self.save_btn.setEnabled(True)

    def listen_server(self):
        while True:
            try:
                data = self.sock.recv(4096)
                if not data:
                    break
                msg = pickle.loads(data)
                # Передаём «msg» в главный поток
                self.newServerMessage.emit(msg)
            except OSError:
                break
            except Exception as e:
                print("[ERROR] listen_server:", e)
                break

        if self.sock:
            self.sock.close()
        self.sock = None
        print("[INFO] Disconnected from server.")

    def onServerMessageMainThread(self, msg):
        msg_type = msg.get('type')
        msg_data = msg.get('data', {})

        if msg_type == 'update_state':
            grid = msg_data.get('grid', [])
            self.is_round_active = msg_data.get('round_active', False)
            self.update_grid(grid)

        elif msg_type == 'chat_broadcast':
            from_user = msg_data.get('from_user', '???')
            text = msg_data.get('text', '')
            self.chat_area.append(f"<b>{from_user}:</b> {text}")

        elif msg_type == 'round_over':
            self.is_round_active = False
            msg_text = msg_data.get('msg', "Раунд завершён.")
            QMessageBox.information(self, "Round Over", msg_text)

        elif msg_type == 'save_ok':
            fname = msg_data
            QMessageBox.information(self, "Saved", f"Server saved field to: {fname}")

        elif msg_type == 'error':
            QMessageBox.warning(self, "Server Error", str(msg_data))

        else:
            print("[WARN] Unknown message:", msg_type, msg_data)

    def update_grid(self, grid):

        rows = len(grid)
        if rows == 0:
            return
        cols = len(grid[0])
        for y in range(rows):
            for x in range(cols):
                color = grid[y][x]
                self.buttons[y][x].setStyleSheet(
                    f"background-color: {color}; border: 1px solid #CCC;"
                )

    def choose_color(self):
        dlg = QColorDialog(self)
        if dlg.exec():
            chosen = dlg.selectedColor()
            if chosen.isValid():
                self.current_color = chosen.name()
                if self.sock:
                    msg = {
                        'type': 'color',
                        'data': {
                            'color': self.current_color
                        }
                    }
                    self.send_msg(msg)

    def send_save(self):
        if not self.sock:
            return
        msg = {'type': 'save', 'data': None}
        self.send_msg(msg)

    def on_send_chat(self):
        text = self.chat_input.text().strip()
        if text and self.sock:
            msg = {
                'type': 'chat',
                'data': {'text': text}
            }
            self.send_msg(msg)
            self.chat_input.clear()

    def send_msg(self, msg_dict):
        if not self.sock:
            return
        try:
            data = pickle.dumps(msg_dict)
            self.sock.sendall(data)
        except Exception as e:
            print("[ERROR] send_msg:", e)

    def closeEvent(self, event):
        if self.sock:
            quit_msg = {'type': 'quit', 'data': None}
            self.send_msg(quit_msg)
        super().closeEvent(event)

def main():
    app = QApplication(sys.argv)
    client = PixelBattleClient()
    client.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()