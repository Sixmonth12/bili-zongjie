using System;using System.IO;using System.Windows.Forms;using System.Reflection;
class Installer {
 [STAThread] static void Main(){try{
 string target=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Programs","ZhizhenOnline");
 if(MessageBox.Show("将安装知帧到当前用户目录并创建桌面快捷方式。无需管理员权限。","安装知帧",MessageBoxButtons.OKCancel)!=DialogResult.OK)return;
 Directory.CreateDirectory(target);string exe=Path.Combine(target,"Zhizhen-Online.exe");
 using(Stream source=Assembly.GetExecutingAssembly().GetManifestResourceStream("Zhizhen-Online.exe"))using(Stream dest=File.Create(exe)){source.CopyTo(dest);}
 string desktop=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),"知帧在线学习.lnk");
 Type t=Type.GetTypeFromProgID("WScript.Shell");object shell=Activator.CreateInstance(t);object shortcut=t.InvokeMember("CreateShortcut",BindingFlags.InvokeMethod,null,shell,new object[]{desktop});
 shortcut.GetType().InvokeMember("TargetPath",BindingFlags.SetProperty,null,shortcut,new object[]{exe});shortcut.GetType().InvokeMember("Save",BindingFlags.InvokeMethod,null,shortcut,new object[]{});
 File.WriteAllText(Path.Combine(target,"卸载说明.txt"),"关闭知帧后删除本目录和桌面快捷方式即可卸载。学习数据单独保存在 在线服务器的个人账号中，卸载不会自动删除。");
 MessageBox.Show("安装完成。双击桌面上的知帧在线学习启动。","知帧");
 }catch(Exception e){MessageBox.Show("安装失败："+e.Message);}}
}
