import tkinter as tk
from tkinter import ttk, messagebox
import os
import configparser
import shutil
from pathlib import Path


class PluginManager:
    def __init__(self, root):
        self.root = root
        self.root.title("IKEMEN-Go Plugin Manager")
        self.root.geometry("900x600")

        # Paths
        self.config_path = Path("./save/config.ini")
        self.backup_path = Path("./save/config.ini.backup")
        self.plugin_dir = Path("./data")

        # Plugin data
        self.all_plugins = {}  # path -> name
        self.enabled_plugins = []  # list of paths in order
        self.original_plugins = []  # track original state for change detection

        self.setup_ui()
        self.load_plugins()

    def setup_ui(self):
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(1, weight=1)

        # Left side - Available plugins
        left_label = ttk.Label(main_frame, text="Available Plugins", font=("", 10, "bold"))
        left_label.grid(row=0, column=0, sticky=tk.W, pady=(0, 5))

        left_frame = ttk.Frame(main_frame)
        left_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))

        self.available_listbox = tk.Listbox(left_frame, width=40, height=20)
        left_scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.available_listbox.yview)
        self.available_listbox.config(yscrollcommand=left_scrollbar.set)

        self.available_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        left_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Middle - Control buttons
        middle_frame = ttk.Frame(main_frame)
        middle_frame.grid(row=1, column=1, padx=10)

        ttk.Button(middle_frame, text="Add →", command=self.add_plugin, width=15).pack(pady=5)
        ttk.Button(middle_frame, text="← Remove", command=self.remove_plugin, width=15).pack(pady=5)

        ttk.Separator(middle_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=20)

        ttk.Button(middle_frame, text="↑ Move Up", command=self.move_up, width=15).pack(pady=5)
        ttk.Button(middle_frame, text="↓ Move Down", command=self.move_down, width=15).pack(pady=5)

        # Right side - Enabled plugins
        right_label = ttk.Label(main_frame, text="Enabled Plugins (Load Order)", font=("", 10, "bold"))
        right_label.grid(row=0, column=2, sticky=tk.W, pady=(0, 5))

        right_frame = ttk.Frame(main_frame)
        right_frame.grid(row=1, column=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(5, 0))
        main_frame.columnconfigure(2, weight=1)

        self.enabled_listbox = tk.Listbox(right_frame, width=40, height=20)
        right_scrollbar = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=self.enabled_listbox.yview)
        self.enabled_listbox.config(yscrollcommand=right_scrollbar.set)

        self.enabled_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        right_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Bottom - Action buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=3, pady=(10, 0))

        # Create custom style for bold button
        style = ttk.Style()
        style.configure("Bold.TButton", font=("", 10, "bold"))

        self.save_button = ttk.Button(button_frame, text="Save Configuration", command=self.save_config, width=20)
        self.save_button.pack(side=tk.LEFT, padx=5)

        ttk.Button(button_frame, text="Reload", command=self.load_plugins, width=20).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Reset to Default", command=self.set_to_default, width=20).pack(side=tk.LEFT, padx=5)

        self.status_label = ttk.Label(main_frame, text="Ready", relief=tk.SUNKEN)
        self.status_label.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(10, 0))

    def get_plugin_name(self, filepath):
        """Extract plugin name from file or use filename"""
        # Lines that are not titles (case-insensitive check)
        NOT_TITLES = [
            'global states (not halted by pause/superpause, no helper limitations)',
            'functions',
            'configuration'
        ]

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()

                # 1. Check if first line is blank
                if not first_line:
                    return filepath.name

                # 2. Check if first line doesn't start with # (not a comment)
                if not first_line.startswith('#'):
                    return filepath.name

                # 3. Check if first line is blank after removing # (just a comment with no content)
                content = first_line[1:].strip()
                if not content:
                    return filepath.name

                # 4. Check if first line is all equals signs
                if set(content) == {'='}:
                    # Read the next line
                    second_line = f.readline().strip()
                    if second_line.startswith('#'):
                        content = second_line[1:].strip()
                    else:
                        return filepath.name

                # 5. Check if content is in the "not titles" list (case-insensitive)
                if content.lower() in NOT_TITLES:
                    return filepath.name

                # 6. Use the content as the title
                if content:
                    return content

        except Exception as e:
            print(f"Error reading {filepath}: {e}")

        # Fallback to filename
        return filepath.name

    def find_all_plugins(self):
        """Recursively find all .zss files"""
        plugins = {}
        if not self.plugin_dir.exists():
            messagebox.showerror("Error", f"Plugin directory not found: {self.plugin_dir}")
            return plugins

        for zss_file in self.plugin_dir.rglob("*.zss"):
            rel_path = zss_file.relative_to(Path("."))
            name = self.get_plugin_name(zss_file)
            plugins[str(rel_path).replace("\\", "/")] = name

        return plugins

    def plugins_line_parser(self, line):
        # Split by comma and strip whitespace
        plugins = [p.strip() for p in line.split(',') if p.strip()]
        return plugins

    def load_enabled_plugins(self):
        """Load enabled plugins from config.ini"""
        if not self.config_path.exists():
            messagebox.showerror("Error", f"Config file not found: {self.config_path}")
            return []

        try:
            config = configparser.ConfigParser()
            config.optionxform = str  # Preserve case for option names
            config.read(self.config_path)

            if 'Common' in config and 'States' in config['Common']:
                states_line = config['Common']['States']
                plugins = self.plugins_line_parser(states_line)
                return plugins
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read config: {e}")

        return []

    def has_unsaved_changes(self):
        """Check if current plugin list differs from original"""
        return self.enabled_plugins != self.original_plugins

    def update_save_button(self):
        """Update save button appearance based on unsaved changes"""
        if self.has_unsaved_changes():
            self.save_button.configure(style="Bold.TButton")
        else:
            self.save_button.configure(style="TButton")

    def load_plugins(self):
        """Load and display all plugins"""
        self.status_label.config(text="Loading plugins...")
        self.root.update()

        # Find all plugins
        self.all_plugins = self.find_all_plugins()

        # Load enabled plugins
        self.enabled_plugins = self.load_enabled_plugins()
        self.original_plugins = self.enabled_plugins.copy()

        # Update listboxes
        self.update_listboxes()
        self.update_save_button()

        self.status_label.config(text=f"Loaded {len(self.all_plugins)} total plugins, {len(self.enabled_plugins)} enabled")

    def update_listboxes(self):
        """Refresh both listboxes"""
        # Clear both
        self.available_listbox.delete(0, tk.END)
        self.enabled_listbox.delete(0, tk.END)

        # Populate enabled list
        for path in self.enabled_plugins:
            name = self.all_plugins.get(path, path)
            self.enabled_listbox.insert(tk.END, f"{name}")

        # Populate available list (exclude enabled ones)
        for path, name in sorted(self.all_plugins.items(), key=lambda x: x[1].lower()):
            if path not in self.enabled_plugins:
                self.available_listbox.insert(tk.END, f"{name}")

    def add_plugin(self):
        """Add selected plugin from available to enabled"""
        selection = self.available_listbox.curselection()
        if not selection:
            return

        idx = selection[0]
        selected_name = self.available_listbox.get(idx)

        # Find the path for this name
        for path, name in self.all_plugins.items():
            if name == selected_name and path not in self.enabled_plugins:
                self.enabled_plugins.append(path)
                self.update_listboxes()
                self.update_save_button()
                self.status_label.config(text=f"Added: {name}")
                break

    def remove_plugin(self):
        """Remove selected plugin from enabled"""
        selection = self.enabled_listbox.curselection()
        if not selection:
            return

        idx = selection[0]
        path = self.enabled_plugins[idx]
        name = self.all_plugins.get(path, path)

        self.enabled_plugins.pop(idx)
        self.update_listboxes()
        self.update_save_button()
        self.status_label.config(text=f"Removed: {name}")

    def move_up(self):
        """Move selected plugin up in load order"""
        selection = self.enabled_listbox.curselection()
        if not selection or selection[0] == 0:
            return

        idx = selection[0]
        self.enabled_plugins[idx], self.enabled_plugins[idx-1] = \
            self.enabled_plugins[idx-1], self.enabled_plugins[idx]

        self.update_listboxes()
        self.enabled_listbox.selection_set(idx-1)
        self.update_save_button()
        self.status_label.config(text="Moved up")

    def move_down(self):
        """Move selected plugin down in load order"""
        selection = self.enabled_listbox.curselection()
        if not selection or selection[0] == len(self.enabled_plugins) - 1:
            return

        idx = selection[0]
        self.enabled_plugins[idx], self.enabled_plugins[idx+1] = \
            self.enabled_plugins[idx+1], self.enabled_plugins[idx]

        self.update_listboxes()
        self.enabled_listbox.selection_set(idx+1)
        self.update_save_button()
        self.status_label.config(text="Moved down")

    def set_to_default(self):
        """Restore the default V-IKEMEN plugin configuration"""
        default_plugin_line = 'data/VPFG_2.0/module/VP_Functions.zss, data/guardbreak.zss, data/score.zss, data/training.zss, data/VPFG_2.0/attackdata.zss, data/VPFG_2.0/autostagecamera.zss, data/VPFG_2.0/module/VP_Commentator.zss, data/VPFG_2.0/module/VP_Action.zss, data/VPFG_2.0/module/VP_Duel.zss, data/VPFG_2.0/module/VP_Results.zss, data/VPFG_2.0/module/VP_WallHit.zss, data/VPFG_2.0/module/VP_CriticalHit.zss, data/VPFG_2.0/module/VP_InkHitSpark.zss, data/VPFG_2.0/module/VP_ComboBreaker.zss, data/VPFG_2.0/module/VP_RushCancel.zss, data/VPFG_2.0/module/VP_Echo.zss, data/VPFG_2.0/module/VP_Aura.zss, data/VPFG_2.0/module/VP_Dramatic.zss, data/VPFG_2.0/module/VP_HeatDrive.zss, data/VPFG_2.0/module/VP_Clash.zss, data/VPFG_2.0/module/VP_Portrait.zss, data/VPFG_2.0/module/VP_Tag.zss, data/VPFG_2.0/module/VP_Win.zss, data/VPFG_2.0/module/VP_Debuff.zss, data/VPFG_2.0/module/VP_ComeBack.zss, data/VPFG_2.0/module/VP_Item.zss, data/VPFG_2.0/module/VP_Meta.zss, data/VPFG_2.0/module/VP_Special.zss, data/VPFG_2.0/module/VP_Stage.zss, data/VPFG_2.0/module/VP_SpecialIntro.zss, data/VPFG_2.0/module/VP_Intro.zss'

        default_plugin_list = self.plugins_line_parser(default_plugin_line)
        self.enabled_plugins = default_plugin_list

        # update listbox with new plugin list
        self.update_listboxes()
        self.update_save_button()

        self.status_label.config(text="Restored default plugin list.")

    def create_backup(self):
        """Create backup of config.ini if it doesn't exist"""
        if not self.backup_path.exists() and self.config_path.exists():
            print(f'couldn\'t find {self.backup_path}, so making a new backup')
            try:
                shutil.copy2(self.config_path, self.backup_path)
                return True
            except Exception as e:
                messagebox.showwarning("Backup Warning",
                    f"Could not create backup: {e}\n\nProceeding anyway, but comments in config.ini may be lost.")
                return False
        return True

    def save_config(self):
        """Save enabled plugins back to config.ini"""
        try:
            # Create backup before first save
            self.create_backup()

            config = configparser.ConfigParser()
            config.optionxform = str  # Preserve case for option names
            config.read(self.config_path)

            # Create States line
            states_line = ", ".join(self.enabled_plugins)

            if 'Common' not in config:
                config['Common'] = {}

            config['Common']['States'] = states_line

            # Write back to file
            with open(self.config_path, 'w') as f:
                config.write(f)

            # Update original_plugins to reflect saved state
            self.original_plugins = self.enabled_plugins.copy()
            self.update_save_button()

            # messagebox.showinfo("Success", "Configuration saved successfully!")
            self.status_label.config(text="Configuration saved")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save config: {e}")
            self.status_label.config(text="Save failed")


def main():
    root = tk.Tk()
    app = PluginManager(root)
    root.mainloop()


if __name__ == "__main__":
    main()
