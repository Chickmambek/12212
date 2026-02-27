import os
import zipfile
import tkinter as tk
from tkinter import filedialog, messagebox
import paramiko
from scp import SCPClient


class UploaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Python File & Folder Uploader")
        self.root.geometry("500x600")

        # We store tuples: (path, is_directory)
        self.selected_items = []

        # --- Item Selection Section ---
        tk.Label(root, text="Step 1: Select Items to Zip", font=('Arial', 10, 'bold')).pack(pady=10)
        self.item_listbox = tk.Listbox(root, width=60, height=10)
        self.item_listbox.pack(padx=20, pady=5)

        btn_frame = tk.Frame(root)
        btn_frame.pack()
        tk.Button(btn_frame, text="Add Files", command=self.add_files).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Add Directory", command=self.add_directory).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Clear", command=self.clear_list).pack(side=tk.LEFT, padx=5)

        # --- Server Details Section ---
        tk.Label(root, text="Step 2: Server Details", font=('Arial', 10, 'bold')).pack(pady=10)

        self.entries = {}
        fields = [('IP Address', 'host'), ('Username', 'user'), ('Password', 'pass'), ('Remote Path', 'path')]
        for label, key in fields:
            row = tk.Frame(root)
            row.pack(fill=tk.X, padx=50, pady=2)
            tk.Label(row, text=label, width=12, anchor='w').pack(side=tk.LEFT)
            ent = tk.Entry(row, show="*" if key == 'pass' else "")
            ent.pack(side=tk.RIGHT, expand=tk.YES, fill=tk.X)
            if key == 'user': ent.insert(0, "root")
            if key == 'path': ent.insert(0, "/tmp")
            self.entries[key] = ent

        # --- Action Button ---
        self.send_btn = tk.Button(root, text="ZIP AND SEND PACKAGE", bg="#2196F3", fg="white",
                                  font=('Arial', 12, 'bold'), command=self.process_and_upload)
        self.send_btn.pack(pady=20, ipadx=20, ipady=5)

    def add_files(self):
        files = filedialog.askopenfilenames(title="Choose files")
        for f in files:
            if f not in [x[0] for x in self.selected_items]:
                self.selected_items.append((f, False))
                self.item_listbox.insert(tk.END, f"📄 {os.path.basename(f)}")

    def add_directory(self):
        dir_path = filedialog.askdirectory(title="Choose directory")
        if dir_path and dir_path not in [x[0] for x in self.selected_items]:
            self.selected_items.append((dir_path, True))
            self.item_listbox.insert(tk.END, f"📁 {os.path.basename(dir_path)}/")

    def clear_list(self):
        self.selected_items = []
        self.item_listbox.delete(0, tk.END)

    def create_zip(self, zip_name):
        with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for path, is_dir in self.selected_items:
                if is_dir:
                    # Walk through the directory and add everything
                    base_name = os.path.basename(path)
                    for root, dirs, files in os.walk(path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            # Create an archive name that preserves the folder structure
                            arcname = os.path.join(base_name, os.path.relpath(file_path, path))
                            zipf.write(file_path, arcname)
                else:
                    # It's just a single file
                    zipf.write(path, os.path.basename(path))

    def process_and_upload(self):
        if not self.selected_items:
            messagebox.showerror("Error", "Please select files or folders first!")
            return

        zip_name = "deploy_package.zip"
        host = self.entries['host'].get()
        user = self.entries['user'].get()
        password = self.entries['pass'].get()
        remote_path = self.entries['path'].get()

        if not host or not password:
            messagebox.showerror("Error", "Server IP and Password required!")
            return

        try:
            self.create_zip(zip_name)

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(host, username=user, password=password)

            with SCPClient(ssh.get_transport()) as scp:
                scp.put(zip_name, remote_path)

            ssh.close()
            os.remove(zip_name)
            messagebox.showinfo("Success", "Files and Folders zipped and uploaded successfully!")

        except Exception as e:
            if os.path.exists(zip_name): os.remove(zip_name)
            messagebox.showerror("Error", f"Operation failed: {str(e)}")


if __name__ == "__main__":
    root = tk.Tk()
    app = UploaderApp(root)
    root.mainloop()