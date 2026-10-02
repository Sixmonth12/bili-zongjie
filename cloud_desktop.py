import json
import os
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from urllib.parse import urlparse
import webbrowser

def main():
    path=Path(os.getenv('LOCALAPPDATA',str(Path.home())))/'ZhizhenOnline'/'service.txt'
    root=tk.Tk();root.title('知帧 · 多人测试版');root.geometry('560x240')
    tk.Label(root,text='连接你的在线学习空间',font=('Microsoft YaHei',18)).pack(pady=20)
    tk.Label(root,text='填写管理员提供的 HTTPS 地址。登录后使用自己的模型 API Key。').pack()
    value=tk.Entry(root,width=65);value.pack(pady=18)
    if path.exists():value.insert(0,path.read_text())
    def launch():
        url=value.get().strip();parsed=urlparse(url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:
            messagebox.showerror('地址无效','请输入 HTTPS 服务地址，不要在地址中填写密码。');return
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(url)
        webbrowser.open(url)
    tk.Button(root,text='打开学习空间',command=launch).pack()
    root.mainloop()
if __name__=='__main__':main()
