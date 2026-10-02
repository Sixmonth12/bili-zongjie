import os
import socket
import secrets
import threading
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
import webbrowser

os.environ['STUDY_DATA_DIR']=str(Path(os.getenv('LOCALAPPDATA',Path.home()))/'BiliStudy'/'data')
import server

def main():
    root=tk.Tk();root.title('知帧 · 学习服务');root.geometry('620x370');root.configure(bg='#e8f5ff')
    server.init_db()
    try:
        http=server.ThreadingHTTPServer(('127.0.0.1',8766),server.Handler)
    except OSError:
        messagebox.showerror('服务已启动','8766 端口已被占用，请关闭已有知帧服务。');root.destroy();return
    threading.Thread(target=http.serve_forever,daemon=True).start()
    tk.Label(root,text='知帧 · 你的学习空间',font=('Microsoft YaHei',20),bg='#e8f5ff',fg='#246ba0').pack(pady=20)
    tk.Button(root,text='打开电脑 App',command=lambda:webbrowser.open('http://127.0.0.1:8766/'),width=25).pack(pady=8)
    tk.Label(root,text='手机：与电脑连接同一 Wi-Fi，启用后复制配对地址到 Android App。',bg='#e8f5ff',wraplength=560).pack(pady=12)
    address=tk.Entry(root,width=78);address.pack(padx=20,pady=8)
    lan=[None]
    def enable():
        if lan[0]:return
        ip=socket.gethostbyname(socket.gethostname())
        try:
            candidate=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);candidate.connect(('192.0.2.1',80));ip=candidate.getsockname()[0];candidate.close()
        except OSError:pass
        if ip.startswith('127.'):
            messagebox.showerror('未找到局域网地址','请连接 Wi-Fi 后重启。');return
        server.PAIR_TOKEN=secrets.token_urlsafe(32)
        server.ALLOWED_HOSTS={ip+':8767'}
        try:lan[0]=server.ThreadingHTTPServer(('0.0.0.0',8767),server.Handler)
        except OSError:messagebox.showerror('端口占用','8767 端口不可用。');return
        threading.Thread(target=lan[0].serve_forever,daemon=True).start()
        address.insert(0,'http://'+ip+':8767/pair?token='+server.PAIR_TOKEN)
        messagebox.showinfo('手机连接已启用','仅在可信家庭网络使用。此地址具有访问学习资料及模型的权限，请勿分享。若 Windows 提示防火墙，请只允许专用网络。')
    tk.Button(root,text='启用手机连接（可信局域网）',command=enable).pack(pady=8)
    def copy():root.clipboard_clear();root.clipboard_append(address.get())
    tk.Button(root,text='复制配对地址',command=copy).pack()
    tk.Label(root,text='关闭此窗口将停止服务；学习记录保存在本机用户目录。',bg='#e8f5ff').pack(pady=12)
    def close():
        http.shutdown()
        if lan[0]:lan[0].shutdown()
        root.destroy()
    root.protocol('WM_DELETE_WINDOW',close)
    webbrowser.open('http://127.0.0.1:8766/')
    root.mainloop()

if __name__=='__main__':main()
