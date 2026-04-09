#!/usr/bin/env python3
"""
🎵 UTC Time Recorder - Modern UI Version
===============================================
Modern cross-platform GUI application
"""

import time
import datetime
import json
import csv
import sys
import os
import threading
import platform
from pathlib import Path
from collections import deque

# ============================================
# Import UI Libraries
# ============================================
try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    HAS_TKINTER = True
except ImportError:
    HAS_TKINTER = False
    print("❌ Tkinter not available")

try:
    import customtkinter as ctk
    HAS_CUSTOMTKINTER = True
except ImportError:
    HAS_CUSTOMTKINTER = False
    print("⚠️  customtkinter not available, using standard Tkinter")

# ============================================
# Keyboard Library Selection
# ============================================
def setup_keyboard_library():
    """Setup keyboard library"""
    try:
        # Try pynput first
        from pynput import keyboard
        return keyboard, 'pynput'
    except ImportError:
        try:
            # Alternative: keyboard library
            import keyboard
            return keyboard, 'keyboard'
        except ImportError:
            return None, None

KEYBOARD_LIB, KEYBOARD_LIB_NAME = setup_keyboard_library()

# ============================================
# Configuration Class
# ============================================
class ConfigManager:
    """Configuration Manager"""
    
    def __init__(self):
        # Use the script directory (to ensure config file stays with the code)
        script_dir = Path(__file__).parent.resolve()
        self.config_file = script_dir / "music_beat_config.json"
        print(f"[Config] Config file path: {self.config_file}")  # debug info
        
        self.default_config = {
            "hotkeys": {
                "start_stop": "F2",
                "beat": "SPACE",
                "exit": "ESC"
            },
            "theme": "dark",
            "bpm_window": 10,
            "auto_save": True,
            "output_format": ["json", "csv"],
            "platform": platform.system(),
            "output_dir": str(Path.home() / "MusicBeatRecordings")
        }
        self.config = self.load_config()
        
        # Ensure output directory exists
        output_dir = Path(self.config.get("output_dir", self.default_config["output_dir"]))
        output_dir.mkdir(exist_ok=True, parents=True)
    
    def load_config(self):
        """Load configuration"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                print(f"[Config] Configuration loaded")
                
                # Merge configurations
                config = self.default_config.copy()
                
                # Deep merge for nested dictionaries
                for key, value in user_config.items():
                    if key in config and isinstance(config[key], dict) and isinstance(value, dict):
                        config[key].update(value)
                    else:
                        config[key] = value
                
                return config
            except Exception as e:
                print(f"[Config] Error loading config: {e}")
                return self.default_config
        else:
            print("[Config] Config file does not exist, creating default config")
            self.save_config(self.default_config)
            return self.default_config
    
    def save_config(self, config=None):
        """Save configuration"""
        if config is None:
            config = self.config
        
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            print(f"[Config] Config saved to {self.config_file}")
            
            # Optional: simple verification after saving
            with open(self.config_file, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            if saved.get("hotkeys") == config.get("hotkeys"):
                print("[Config] Config verification passed")
            else:
                print("[Config] Warning: saved config does not match memory config")
            return True
        except Exception as e:
            print(f"[Config] Error saving config: {e}")
            return False
    
    def update_config(self, key, value):
        """Update configuration"""
        keys = key.split('.')
        config = self.config
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
        return self.save_config()

# ============================================
# Core Recording Class
# ============================================
class BeatRecorderCore:
    """Core recording functionality"""
    
    def __init__(self, config_manager):
        self.config = config_manager
        self.recordings = []
        self.is_recording = False
        self.start_time = None
        
        # Use configured output directory
        self.output_dir = Path(self.config.config.get("output_dir", "music_beat_recordings"))
        self.output_dir.mkdir(exist_ok=True, parents=True)
        
        # BPM calculation
        self.recent_beats = deque(maxlen=50)
        self.bpm_history = []
        
        # Statistics
        self.stats = {
            "total_beats": 0,
            "total_time": 0,
            "avg_bpm": 0,
            "current_bpm": 0,
            "max_bpm": 0,
            "min_bpm": float('inf')
        }
        
        # Listener
        self.listener = None
        self.keyboard_lib = KEYBOARD_LIB
        self.lib_name = KEYBOARD_LIB_NAME
        
        # Callback functions (for UI updates)
        self.on_beat_callback = None
        self.on_status_change = None
        self.on_bpm_update = None
        
        # Thread safety
        self.lock = threading.Lock()
    
    def start_recording(self):
        """Start recording"""
        if self.is_recording:
            return False
        
        with self.lock:
            self.is_recording = True
            self.start_time = time.time()
            self.recordings.append({
                "event": "start",
                "timestamp": self.start_time,
                "utc_time": datetime.datetime.utcnow().isoformat() + "Z",
                "local_time": datetime.datetime.now().isoformat()
            })
            
            # Update status
            if self.on_status_change:
                self.on_status_change(True, self.start_time)
            
            return True
    
    def stop_recording(self):
        """Stop recording"""
        if not self.is_recording:
            return False
        
        with self.lock:
            self.is_recording = False
            stop_time = time.time()
            self.recordings.append({
                "event": "stop",
                "timestamp": stop_time,
                "utc_time": datetime.datetime.utcnow().isoformat() + "Z",
                "local_time": datetime.datetime.now().isoformat()
            })
            
            # Calculate total time
            if self.start_time:
                duration = stop_time - self.start_time
                self.stats["total_time"] = duration
            
            # Update status
            if self.on_status_change:
                self.on_status_change(False, stop_time)
            
            return True
    
    def record_beat(self):
        """Record a beat"""
        if not self.is_recording:
            return False
        
        with self.lock:
            beat_time = time.time()
            
            # Calculate offset
            offset = 0
            if self.start_time:
                offset = beat_time - self.start_time
            
            # Calculate BPM before adding beat
            old_bpm = self.stats["current_bpm"]
            
            # Add recording
            recording = {
                "event": "beat",
                "timestamp": beat_time,
                "utc_time": datetime.datetime.utcnow().isoformat() + "Z",
                "local_time": datetime.datetime.now().isoformat(),
                "offset": round(offset, 3),
                "beat_number": self.stats["total_beats"] + 1
            }
            
            self.recordings.append(recording)
            self.recent_beats.append(beat_time)
            self.stats["total_beats"] += 1
            
            # Calculate BPM
            bpm = self.calculate_bpm()
            self.stats["current_bpm"] = bpm
            
            # Update min/max BPM
            if bpm > 0:
                if bpm > self.stats["max_bpm"]:
                    self.stats["max_bpm"] = bpm
                if bpm < self.stats["min_bpm"]:
                    self.stats["min_bpm"] = bpm
            
            # Update callbacks
            if self.on_beat_callback:
                self.on_beat_callback(recording)
            
            if self.on_bpm_update and bpm != old_bpm:
                self.on_bpm_update(bpm)
            
            return True
    
    def calculate_bpm(self):
        """Calculate real-time BPM"""
        if len(self.recent_beats) < 2:
            return 0
        
        # Calculate intervals between recent beats
        intervals = []
        beats = list(self.recent_beats)
        
        for i in range(1, len(beats)):
            interval = beats[i] - beats[i-1]
            if interval > 0:  # Avoid division by zero
                intervals.append(interval)
        
        if not intervals:
            return 0
        
        # Calculate BPM using recent N intervals
        n = min(self.config.config.get("bpm_window", 10), len(intervals))
        recent_intervals = intervals[-n:]
        
        avg_interval = sum(recent_intervals) / len(recent_intervals)
        
        if avg_interval > 0:
            return round(60 / avg_interval, 1)
        
        return 0
    
    def save_data(self, format_type="both"):
        """Save data"""
        if not self.recordings:
            return False, "No data to save"
        
        timestamp = datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        base_name = f"music_beats_{timestamp}"
        
        # Extract beat data
        beats = [r for r in self.recordings if r["event"] == "beat"]
        starts = [r for r in self.recordings if r["event"] == "start"]
        stops = [r for r in self.recordings if r["event"] == "stop"]
        
        # Calculate statistics
        total_duration = 0
        session_start = None
        session_end = None
        
        if starts:
            session_start = starts[0]["timestamp"]
        if stops:
            session_end = stops[-1]["timestamp"]
        
        if session_start and session_end:
            total_duration = session_end - session_start
        
        # Calculate average BPM
        avg_bpm = 0
        if len(beats) >= 2 and total_duration > 0:
            avg_bpm = round(60 * len(beats) / total_duration, 1)
        
        metadata = {
            "session": {
                "start_time": starts[0]["utc_time"] if starts else None,
                "end_time": stops[-1]["utc_time"] if stops else None,
                "total_duration": round(total_duration, 3),
                "total_beats": len(beats),
                "avg_bpm": avg_bpm,
                "max_bpm": self.stats["max_bpm"],
                "min_bpm": self.stats["min_bpm"] if self.stats["min_bpm"] != float('inf') else 0,
                "platform": platform.system(),
                "version": "1.1"
            },
            "recordings": self.recordings
        }
        
        saved_files = []
        
        # Save as JSON
        if format_type in ["json", "both"]:
            json_path = self.output_dir / f"{base_name}.json"
            try:
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False, default=str)
                saved_files.append(str(json_path))
            except Exception as e:
                return False, f"Failed to save JSON: {e}"
        
        # Save as CSV
        if format_type in ["csv", "both"]:
            csv_path = self.output_dir / f"{base_name}.csv"
            try:
                with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['No.', 'Event Type', 'Local Time', 'UTC Time', 'Timestamp', 'Offset(seconds)', 'Beat Number'])
                    
                    for i, record in enumerate(self.recordings, 1):
                        writer.writerow([
                            i,
                            record['event'],
                            record.get('local_time', ''),
                            record['utc_time'],
                            record['timestamp'],
                            record.get('offset', ''),
                            record.get('beat_number', '')
                        ])
                saved_files.append(str(csv_path))
            except Exception as e:
                return False, f"Failed to save CSV: {e}"
        
        return True, f"Data saved to:\n" + "\n".join(saved_files)
    
    def clear_data(self):
        """Clear data"""
        with self.lock:
            self.recordings.clear()
            self.recent_beats.clear()
            self.bpm_history.clear()
            self.stats = {
                "total_beats": 0,
                "total_time": 0,
                "avg_bpm": 0,
                "current_bpm": 0,
                "max_bpm": 0,
                "min_bpm": float('inf')
            }
            self.is_recording = False
            self.start_time = None
    
    def get_summary(self):
        """Get summary information"""
        with self.lock:
            beats = [r for r in self.recordings if r["event"] == "beat"]
            
            summary = {
                "total_beats": len(beats),
                "current_bpm": self.stats["current_bpm"],
                "is_recording": self.is_recording,
                "recording_duration": 0,
                "max_bpm": self.stats["max_bpm"],
                "min_bpm": self.stats["min_bpm"] if self.stats["min_bpm"] != float('inf') else 0
            }
            
            if self.is_recording and self.start_time:
                summary["recording_duration"] = time.time() - self.start_time
            
            return summary
    
    def export_to_file(self, filepath):
        """Export data to a specific file"""
        if not self.recordings:
            return False, "No data to export"
        
        try:
            filepath = Path(filepath)
            if filepath.suffix.lower() == '.json':
                # Export as JSON
                metadata = {
                    "session": {
                        "total_beats": len([r for r in self.recordings if r["event"] == "beat"]),
                        "recordings": self.recordings
                    }
                }
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False, default=str)
                return True, f"Data exported to {filepath}"
            
            elif filepath.suffix.lower() == '.csv':
                # Export as CSV
                with open(filepath, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['No.', 'Event Type', 'Local Time', 'UTC Time', 'Timestamp', 'Offset(seconds)', 'Beat Number'])
                    
                    for i, record in enumerate(self.recordings, 1):
                        writer.writerow([
                            i,
                            record['event'],
                            record.get('local_time', ''),
                            record['utc_time'],
                            record['timestamp'],
                            record.get('offset', ''),
                            record.get('beat_number', '')
                        ])
                return True, f"Data exported to {filepath}"
            
            else:
                return False, "Unsupported file format"
                
        except Exception as e:
            return False, f"Export failed: {e}"

# ============================================
# Modern UI Interface
# ============================================
class MusicBeatRecorderUI:
    """Main UI Interface"""
    
    def __init__(self):
        # Initialize configuration manager
        self.config_manager = ConfigManager()
        
        # Initialize core functionality
        self.recorder = BeatRecorderCore(self.config_manager)
        self.recorder.on_beat_callback = self.on_beat_recorded
        self.recorder.on_status_change = self.on_recording_status_changed
        # BPM update callback is no longer needed for the main display
        # self.recorder.on_bpm_update = self.on_bpm_updated  # REMOVED - main display now shows last beat time
        
        # Keyboard listener
        self.keyboard_listener = None
        self.keyboard_lib_name = KEYBOARD_LIB_NAME  # store for later use
        
        # Create main window
        if HAS_CUSTOMTKINTER:
            ctk.set_appearance_mode(self.config_manager.config.get("theme", "dark"))
            ctk.set_default_color_theme("blue")
            self.root = ctk.CTk()
        else:
            self.root = tk.Tk()
        
        self.root.title("🎵 UTC Time Recorder")
        self.root.geometry("900x700")
        
        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Set window icon (if available)
        self.set_window_icon()
        
        # Create UI components
        self.setup_ui()
        
        # Setup hotkeys
        self.setup_hotkeys()
        
        # Update loop
        self.update_timer()
    
    def set_window_icon(self):
        """Set window icon"""
        try:
            if platform.system() == "Windows":
                self.root.iconbitmap(default="icon.ico")
            # Other platforms can set other icon formats
        except:
            pass
    
    def setup_ui(self):
        """Setup UI interface"""
        # Use grid layout
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        if HAS_CUSTOMTKINTER:
            self.create_modern_ui()
        else:
            self.create_basic_ui()
    
    def create_modern_ui(self):
        """Create modern UI (using customtkinter)"""
        # Main frame
        main_frame = ctk.CTkFrame(self.root)
        main_frame.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        main_frame.grid_rowconfigure(1, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)
        
        # Title bar
        title_frame = ctk.CTkFrame(main_frame, height=60)
        title_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        title_frame.grid_columnconfigure(0, weight=1)
        
        title_label = ctk.CTkLabel(
            title_frame,
            text="🎵 UTC Time Recorder",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.grid(row=0, column=0, padx=20, pady=10)
        
        # Status bar
        status_frame = ctk.CTkFrame(main_frame, height=100)
        status_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        status_frame.grid_columnconfigure((0, 1, 2), weight=1)
        
        # Recording status indicator
        self.status_indicator = ctk.CTkLabel(
            status_frame,
            text="● Stopped",
            text_color="red",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.status_indicator.grid(row=0, column=0, padx=20, pady=10)
        
        # Last beat timestamp display (replaces BPM)
        self.last_beat_label = ctk.CTkLabel(
            status_frame,
            text="Last Beat: --:--:--.---",
            font=ctk.CTkFont(size=28, weight="bold")
        )
        self.last_beat_label.grid(row=0, column=1, padx=20, pady=10)
        
        # Beat counter
        self.beat_counter = ctk.CTkLabel(
            status_frame,
            text="Beats: 0",
            font=ctk.CTkFont(size=16)
        )
        self.beat_counter.grid(row=0, column=2, padx=20, pady=10)
        
        # Control button area
        control_frame = ctk.CTkFrame(main_frame)
        control_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        control_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)
        
        # Start/Stop button
        self.start_button = ctk.CTkButton(
            control_frame,
            text="▶ Start Recording",
            command=self.toggle_recording,
            font=ctk.CTkFont(size=14),
            height=40,
            fg_color="green",
            hover_color="dark green"
        )
        self.start_button.grid(row=0, column=0, padx=10, pady=10)
        
        # Record beat button
        self.beat_button = ctk.CTkButton(
            control_frame,
            text="🥁 Record Beat",
            command=self.record_beat_manual,
            font=ctk.CTkFont(size=14),
            height=40
        )
        self.beat_button.grid(row=0, column=1, padx=10, pady=10)
        
        # Save button
        self.save_button = ctk.CTkButton(
            control_frame,
            text="💾 Save Data",
            command=self.save_data_dialog,
            font=ctk.CTkFont(size=14),
            height=40,
            fg_color="blue"
        )
        self.save_button.grid(row=0, column=2, padx=10, pady=10)
        
        # Clear button
        self.clear_button = ctk.CTkButton(
            control_frame,
            text="🗑️ Clear Data",
            command=self.clear_data_confirm,
            font=ctk.CTkFont(size=14),
            height=40,
            fg_color="gray"
        )
        self.clear_button.grid(row=0, column=3, padx=10, pady=10)
        
        # Beat history area
        history_frame = ctk.CTkFrame(main_frame)
        history_frame.grid(row=3, column=0, sticky="nsew", padx=10, pady=(5, 10))
        history_frame.grid_rowconfigure(0, weight=1)
        history_frame.grid_columnconfigure(0, weight=1)
        
        # History label
        history_label = ctk.CTkLabel(
            history_frame,
            text="📝 Beat History",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        history_label.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="w")
        
        # Beat history table
        columns = ("#", "Time", "Offset", "BPM")
        self.history_tree = ttk.Treeview(
            history_frame,
            columns=columns,
            show="headings",
            height=10
        )
        
        # Setup columns
        self.history_tree.heading("#", text="#")
        self.history_tree.heading("Time", text="Local Time")
        self.history_tree.heading("Offset", text="Offset(seconds)")
        self.history_tree.heading("BPM", text="BPM")
        
        self.history_tree.column("#", width=50, anchor="center")
        self.history_tree.column("Time", width=200)
        self.history_tree.column("Offset", width=100, anchor="center")
        self.history_tree.column("BPM", width=100, anchor="center")
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(history_frame, orient="vertical", command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scrollbar.set)
        
        self.history_tree.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns", pady=(0, 10))
        
        # Bottom status bar
        bottom_frame = ctk.CTkFrame(main_frame, height=40)
        bottom_frame.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 10))
        bottom_frame.grid_columnconfigure(0, weight=1)
        
        self.bottom_label = ctk.CTkLabel(
            bottom_frame,
            text="Ready",
            font=ctk.CTkFont(size=12)
        )
        self.bottom_label.grid(row=0, column=0, padx=10, pady=5, sticky="w")
        
        # Settings area
        settings_button = ctk.CTkButton(
            bottom_frame,
            text="⚙️ Settings",
            command=self.open_settings,
            font=ctk.CTkFont(size=12),
            width=80
        )
        settings_button.grid(row=0, column=1, padx=10, pady=5)
        
        # Export button
        export_button = ctk.CTkButton(
            bottom_frame,
            text="📤 Export",
            command=self.export_data,
            font=ctk.CTkFont(size=12),
            width=80
        )
        export_button.grid(row=0, column=2, padx=10, pady=5)
    
    def create_basic_ui(self):
        """Create basic UI (using standard Tkinter)"""
        # Title
        title_label = tk.Label(
            self.root,
            text="🎵 UTC Time Recorder",
            font=("Arial", 20, "bold")
        )
        title_label.pack(pady=20)
        
        # Status frame
        status_frame = tk.Frame(self.root)
        status_frame.pack(pady=10)
        
        # Status indicator
        self.status_indicator = tk.Label(
            status_frame,
            text="● Stopped",
            fg="red",
            font=("Arial", 14, "bold")
        )
        self.status_indicator.pack(side=tk.LEFT, padx=20)
        
        # Last beat timestamp display (replaces BPM)
        self.last_beat_label = tk.Label(
            status_frame,
            text="Last Beat: --:--:--.---",
            font=("Arial", 24, "bold")
        )
        self.last_beat_label.pack(side=tk.LEFT, padx=20)
        
        # Beat counter
        self.beat_counter = tk.Label(
            status_frame,
            text="Beats: 0",
            font=("Arial", 14)
        )
        self.beat_counter.pack(side=tk.LEFT, padx=20)
        
        # Control button frame
        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=20)
        
        # Start/Stop button
        self.start_button = tk.Button(
            button_frame,
            text="▶ Start Recording",
            command=self.toggle_recording,
            font=("Arial", 12),
            bg="green",
            fg="white",
            width=15,
            height=2
        )
        self.start_button.pack(side=tk.LEFT, padx=10)
        
        # Record beat button
        self.beat_button = tk.Button(
            button_frame,
            text="🥁 Record Beat",
            command=self.record_beat_manual,
            font=("Arial", 12),
            width=15,
            height=2
        )
        self.beat_button.pack(side=tk.LEFT, padx=10)
        
        # Save button
        self.save_button = tk.Button(
            button_frame,
            text="💾 Save Data",
            command=self.save_data_dialog,
            font=("Arial", 12),
            bg="blue",
            fg="white",
            width=15,
            height=2
        )
        self.save_button.pack(side=tk.LEFT, padx=10)
        
        # Clear button
        self.clear_button = tk.Button(
            button_frame,
            text="🗑️ Clear Data",
            command=self.clear_data_confirm,
            font=("Arial", 12),
            bg="gray",
            fg="white",
            width=15,
            height=2
        )
        self.clear_button.pack(side=tk.LEFT, padx=10)
        
        # History area
        history_frame = tk.Frame(self.root)
        history_frame.pack(pady=20, padx=20, fill=tk.BOTH, expand=True)
        
        # History label
        history_label = tk.Label(
            history_frame,
            text="📝 Beat History",
            font=("Arial", 14, "bold")
        )
        history_label.pack(anchor="w", pady=(0, 5))
        
        # Beat history table
        columns = ("#", "Time", "Offset", "BPM")
        self.history_tree = ttk.Treeview(
            history_frame,
            columns=columns,
            show="headings",
            height=12
        )
        
        # Setup columns
        for col in columns:
            self.history_tree.heading(col, text=col)
            self.history_tree.column(col, width=100, anchor="center")
        
        self.history_tree.column("#", width=50)
        self.history_tree.column("Time", width=200)
        
        # Scrollbar
        scrollbar = tk.Scrollbar(history_frame, orient="vertical", command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scrollbar.set)
        
        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bottom status bar
        bottom_frame = tk.Frame(self.root, height=40, bg="lightgray")
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        self.bottom_label = tk.Label(
            bottom_frame,
            text="Ready",
            font=("Arial", 10),
            bg="lightgray"
        )
        self.bottom_label.pack(side=tk.LEFT, padx=10, pady=5)
        
        # Settings button
        settings_button = tk.Button(
            bottom_frame,
            text="⚙️ Settings",
            command=self.open_settings,
            font=("Arial", 10)
        )
        settings_button.pack(side=tk.RIGHT, padx=10, pady=5)
        
        # Export button
        export_button = tk.Button(
            bottom_frame,
            text="📤 Export",
            command=self.export_data,
            font=("Arial", 10)
        )
        export_button.pack(side=tk.RIGHT, padx=10, pady=5)
    
    def setup_hotkeys(self):
        """Setup hotkeys"""
        if not KEYBOARD_LIB:
            self.show_message("Warning", "No keyboard library detected, hotkey functionality unavailable")
            return
        
        try:
            hotkeys = self.config_manager.config["hotkeys"]
            print(f"[Hotkeys] Setting up: {hotkeys}")
            
            if KEYBOARD_LIB_NAME == "pynput":
                self.setup_pynput_hotkeys(hotkeys)
            else:
                self.setup_keyboard_hotkeys(hotkeys)
            
            self.show_bottom_message(f"Hotkeys enabled: {hotkeys['start_stop']} Start/Stop, {hotkeys['beat']} Record Beat, {hotkeys['exit']} Exit")
            
        except Exception as e:
            self.show_message("Error", f"Failed to setup hotkeys: {e}")
    
    def setup_pynput_hotkeys(self, hotkeys):
        """Setup pynput hotkeys"""
        def on_press(key):
            try:
                # Convert key to string representation
                if hasattr(key, 'char') and key.char:
                    key_str = key.char
                else:
                    key_str = str(key).replace("'", "").replace("Key.", "")
                
                # Handle hotkeys
                if key_str.upper() == hotkeys["start_stop"].upper():
                    self.toggle_recording()
                elif key_str.upper() == hotkeys["beat"].upper():
                    self.record_beat_manual()
                elif key_str.upper() == hotkeys["exit"].upper():
                    self.on_closing()
            except Exception as e:
                print(f"Hotkey error: {e}")
        
        def on_release(key):
            # We don't need to do anything on release
            pass
        
        # Start listener thread
        self.keyboard_listener = KEYBOARD_LIB.Listener(on_press=on_press, on_release=on_release)
        self.keyboard_listener.daemon = True
        self.keyboard_listener.start()
    
    def setup_keyboard_hotkeys(self, hotkeys):
        """Setup keyboard library hotkeys"""
        try:
            def start_stop_handler():
                self.toggle_recording()
            
            def beat_handler():
                self.record_beat_manual()
            
            def exit_handler():
                self.on_closing()
            
            KEYBOARD_LIB.add_hotkey(hotkeys["start_stop"].lower(), start_stop_handler)
            KEYBOARD_LIB.add_hotkey(hotkeys["beat"].lower(), beat_handler)
            KEYBOARD_LIB.add_hotkey(hotkeys["exit"].lower(), exit_handler)
            
            # Start listening in a separate thread
            threading.Thread(target=KEYBOARD_LIB.wait, daemon=True).start()
            
        except Exception as e:
            print(f"Error setting up keyboard hotkeys: {e}")
    
    # ============================================
    # Improved hotkey stop and restart methods
    # ============================================
    def stop_hotkeys(self):
        """Stop current hotkey listener (wait for threads to finish)"""
        if self.keyboard_lib_name == 'pynput' and self.keyboard_listener:
            try:
                self.keyboard_listener.stop()
                # Wait for thread to finish, max 0.5 seconds
                self.keyboard_listener.join(timeout=0.5)
            except Exception:
                pass
            finally:
                self.keyboard_listener = None
        elif self.keyboard_lib_name == 'keyboard':
            try:
                KEYBOARD_LIB.unhook_all()
                # keyboard library may need a moment to clean up
                time.sleep(0.1)
            except Exception:
                pass
    
    def restart_hotkeys(self):
        """Restart hotkey listeners with current settings."""
        self.stop_hotkeys()
        # Give the system a moment to release resources
        time.sleep(0.2)

        if not KEYBOARD_LIB:
            return False

        hotkeys = self.config_manager.config["hotkeys"]
        print(f"[Hotkeys] Reloading: {hotkeys}")
        
        try:
            if KEYBOARD_LIB_NAME == "pynput":
                self.setup_pynput_hotkeys(hotkeys)
                return True  # pynput can be updated dynamically
            elif KEYBOARD_LIB_NAME == "keyboard":
                # keyboard library needs to clear all hooks first
                KEYBOARD_LIB.unhook_all()
                self.setup_keyboard_hotkeys(hotkeys)
                return True  # try to update dynamically
        except Exception as e:
            print(f"[ERROR] Failed to restart hotkeys: {e}")
            return False
    
    # ============================================
    # UI Callback Methods
    # ============================================
    def toggle_recording(self):
        """Toggle recording state"""
        if self.recorder.is_recording:
            self.recorder.stop_recording()
        else:
            self.recorder.start_recording()
    
    def record_beat_manual(self):
        """Manually record beat"""
        self.recorder.record_beat()
    
    def on_beat_recorded(self, recording):
        """Beat recorded callback"""
        # Update UI
        beat_num = recording["beat_number"]
        offset = recording["offset"]
        bpm = self.recorder.stats["current_bpm"]
        
        # Update last beat timestamp display
        # Extract local time and format as HH:MM:SS.fff
        local_time_str = recording["local_time"]
        try:
            # local_time is ISO format like "2025-01-15T14:30:25.123456"
            # We want "14:30:25.123"
            if 'T' in local_time_str:
                time_part = local_time_str.split('T')[1].split('.')[0]
                ms_part = local_time_str.split('.')[1][:3] if '.' in local_time_str else '000'
                formatted_time = f"{time_part}.{ms_part}"
            else:
                formatted_time = local_time_str
        except:
            formatted_time = local_time_str
        
        self.last_beat_label.configure(text=f"Last Beat: {formatted_time}")
        
        # Add to history table
        time_str = datetime.datetime.fromtimestamp(recording["timestamp"]).strftime("%H:%M:%S.%f")[:-3]
        
        if HAS_CUSTOMTKINTER:
            self.history_tree.insert("", 0, values=(beat_num, time_str, offset, bpm))
        else:
            self.history_tree.insert("", 0, values=(beat_num, time_str, offset, bpm))
        
        # Update counter
        self.beat_counter.configure(text=f"Beats: {beat_num}")
        
        # Flash beat button effect
        self.flash_beat_button()
    
    def on_recording_status_changed(self, is_recording, timestamp):
        """Recording status changed callback"""
        if is_recording:
            self.status_indicator.configure(text="● Recording", text_color="green" if HAS_CUSTOMTKINTER else "green")
            self.start_button.configure(text="⏸️ Stop Recording", fg_color="red" if HAS_CUSTOMTKINTER else "red")
            self.show_bottom_message("Recording started - Press SPACE for beats, F2 to stop")
        else:
            self.status_indicator.configure(text="● Stopped", text_color="red" if HAS_CUSTOMTKINTER else "red")
            self.start_button.configure(text="▶ Start Recording", fg_color="green" if HAS_CUSTOMTKINTER else "green")
            self.show_bottom_message("Recording stopped")
    
    def on_bpm_updated(self, bpm):
        """BPM updated callback (kept for potential future use, but no longer updates main label)"""
        # This method is no longer bound to the recorder, so it won't be called.
        # If you want to show BPM elsewhere, you can implement it here.
        pass
    
    def flash_beat_button(self):
        """Flash beat button effect"""
        if HAS_CUSTOMTKINTER:
            original_color = self.beat_button.cget("fg_color")
            self.beat_button.configure(fg_color="yellow")
            self.root.after(100, lambda: self.beat_button.configure(fg_color=original_color))
        else:
            original_bg = self.beat_button.cget("bg")
            self.beat_button.configure(bg="yellow")
            self.root.after(100, lambda: self.beat_button.configure(bg=original_bg))
    
    def save_data_dialog(self):
        """Save data dialog"""
        try:
            if not self.recorder.recordings:
                self.show_message("Info", "No data to save")
                return
            
            success, message = self.recorder.save_data("both")
            
            if success:
                self.show_message("Success", message)
                self.show_bottom_message("Data saved successfully")
            else:
                self.show_message("Error", message)
        except Exception as e:
            self.show_message("Error", f"Save failed: {e}")
    
    def export_data(self):
        """Export data to specific file"""
        if not self.recorder.recordings:
            self.show_message("Info", "No data to export")
            return
        
        # Ask for file type
        filetypes = [
            ("JSON files", "*.json"),
            ("CSV files", "*.csv"),
            ("All files", "*.*")
        ]
        
        filename = filedialog.asksaveasfilename(
            title="Export Data",
            defaultextension=".json",
            filetypes=filetypes
        )
        
        if filename:
            success, message = self.recorder.export_to_file(filename)
            if success:
                self.show_message("Success", message)
                self.show_bottom_message("Data exported successfully")
            else:
                self.show_message("Error", message)
    
    def clear_data_confirm(self):
        """Confirm clear data"""
        if not self.recorder.recordings:
            return
        
        if self.show_confirm_dialog("Confirm", "Are you sure you want to clear all data?"):
            try:
                self.recorder.clear_data()
                self.history_tree.delete(*self.history_tree.get_children())
                self.beat_counter.configure(text="Beats: 0")
                self.last_beat_label.configure(text="Last Beat: --:--:--.---")  # Reset timestamp display
                self.show_bottom_message("Data cleared")
            except Exception as e:
                self.show_message("Error", f"Clear failed: {e}")
    
    def open_settings(self):
        """Open settings window"""
        settings_window = SettingsWindow(self)
    
    # ============================================
    # Unified message box methods
    # ============================================
    def show_message(self, title, message):
        """Show message dialog (always use tkinter.messagebox)"""
        messagebox.showinfo(title, message)
    
    def show_confirm_dialog(self, title, message):
        """Show confirmation dialog (always use tkinter.messagebox)"""
        return messagebox.askyesno(title, message)
    
    def show_bottom_message(self, message):
        """Show bottom status message"""
        self.bottom_label.configure(text=message)
    
    def update_timer(self):
        """Timer update for UI"""
        if self.recorder.is_recording and self.recorder.start_time:
            duration = time.time() - self.recorder.start_time
            mins, secs = divmod(int(duration), 60)
            self.show_bottom_message(f"Recording... {mins:02d}:{secs:02d}")
        
        # Update every second
        self.root.after(1000, self.update_timer)
    
    def on_closing(self):
        """Handle window closing"""
        # Stop recording if active
        if self.recorder.is_recording:
            self.recorder.stop_recording()
        
        # Stop keyboard listener
        self.stop_hotkeys()
        
        # Save config
        self.config_manager.save_config()
        
        # Close window
        self.root.destroy()
    
    def run(self):
        """Run main loop"""
        self.root.mainloop()

# ============================================
# Settings Window
# ============================================
class SettingsWindow:
    """Settings Window"""
    
    def __init__(self, parent):
        self.parent = parent
        self.config = parent.config_manager
        
        # Create window
        if HAS_CUSTOMTKINTER:
            self.window = ctk.CTkToplevel(parent.root)
        else:
            self.window = tk.Toplevel(parent.root)
        
        self.window.title("Settings")
        self.window.geometry("500x600")
        self.window.transient(parent.root)
        self.window.grab_set()
        
        # Make modal
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI"""
        if HAS_CUSTOMTKINTER:
            main_frame = ctk.CTkFrame(self.window)
        else:
            main_frame = tk.Frame(self.window)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Title
        if HAS_CUSTOMTKINTER:
            title_label = ctk.CTkLabel(
                main_frame,
                text="⚙️ Settings",
                font=ctk.CTkFont(size=18, weight="bold")
            )
        else:
            title_label = tk.Label(
                main_frame,
                text="⚙️ Settings",
                font=("Arial", 18, "bold")
            )
        title_label.pack(pady=(0, 20))
        
        # Notebook for tabs
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill="both", expand=True, pady=(0, 20))
        
        # Hotkeys tab
        hotkey_frame = ttk.Frame(notebook)
        notebook.add(hotkey_frame, text="Hotkeys")
        self.create_hotkey_tab(hotkey_frame)
        
        # General tab
        general_frame = ttk.Frame(notebook)
        notebook.add(general_frame, text="General")
        self.create_general_tab(general_frame)
        
        # Button frame - fixed at bottom
        button_frame = tk.Frame(main_frame)
        button_frame.pack(side="bottom", fill="x", pady=10)
        
        save_button = self.create_button(button_frame, "💾 Save Settings", self.save_settings)
        save_button.pack(side="left", padx=10)
        
        close_button = self.create_button(button_frame, "Close", self.on_closing)
        close_button.pack(side="right", padx=10)
    
    
    def create_hotkey_tab(self, parent):
        """Create hotkey settings tab"""
        # Instructions - note: only single keys supported
        instructions = tk.Label(
            parent,
            text="Enter single key names (e.g., F2, SPACE, ESC, a, b)\nCombination keys (like Ctrl+A) not supported yet",
            font=("Arial", 10),
            wraplength=400
        )
        instructions.pack(pady=(10, 20))
        
        # Hotkey settings
        hotkeys = self.config.config["hotkeys"]
        
        # Start/Stop hotkey
        start_stop_frame = tk.Frame(parent)
        start_stop_frame.pack(fill="x", padx=20, pady=5)
        
        tk.Label(start_stop_frame, text="Start/Stop Recording:", width=20, anchor="w").pack(side="left")
        self.start_stop_var = tk.StringVar(value=hotkeys.get("start_stop", "F2"))
        tk.Entry(start_stop_frame, textvariable=self.start_stop_var, width=15).pack(side="left", padx=10)
        
        # Beat hotkey
        beat_frame = tk.Frame(parent)
        beat_frame.pack(fill="x", padx=20, pady=5)
        
        tk.Label(beat_frame, text="Record Beat:", width=20, anchor="w").pack(side="left")
        self.beat_var = tk.StringVar(value=hotkeys.get("beat", "SPACE"))
        tk.Entry(beat_frame, textvariable=self.beat_var, width=15).pack(side="left", padx=10)
        
        # Exit hotkey
        exit_frame = tk.Frame(parent)
        exit_frame.pack(fill="x", padx=20, pady=5)
        
        tk.Label(exit_frame, text="Exit Program:", width=20, anchor="w").pack(side="left")
        self.exit_var = tk.StringVar(value=hotkeys.get("exit", "ESC"))
        tk.Entry(exit_frame, textvariable=self.exit_var, width=15).pack(side="left", padx=10)
        
    
    def create_general_tab(self, parent):
        """Create general settings tab"""
        # Theme settings
        theme_frame = tk.LabelFrame(parent, text="Interface Theme", padx=10, pady=10)
        theme_frame.pack(fill="x", padx=20, pady=10)
        
        if HAS_CUSTOMTKINTER:
            self.theme_var = tk.StringVar(value=self.config.config.get("theme", "dark"))
            theme_options = ["dark", "light", "system"]
            
            for option in theme_options:
                rb = tk.Radiobutton(
                    theme_frame,
                    text=option.capitalize(),
                    variable=self.theme_var,
                    value=option,
                    command=lambda o=option: self.change_theme(o)
                )
                rb.pack(anchor="w", pady=2)
        else:
            tk.Label(theme_frame, text="Standard Tkinter doesn't support theme switching").pack(pady=10)
        
        # BPM calculation window
        bpm_frame = tk.LabelFrame(parent, text="BPM Calculation", padx=10, pady=10)
        bpm_frame.pack(fill="x", padx=20, pady=10)
        
        tk.Label(bpm_frame, text="BPM Calculation Window Size:").pack(anchor="w", pady=5)
        
        self.bpm_window_var = tk.IntVar(value=self.config.config.get("bpm_window", 10))
        bpm_scale = tk.Scale(
            bpm_frame,
            from_=5,
            to=50,
            orient="horizontal",
            variable=self.bpm_window_var,
            length=300
        )
        bpm_scale.pack(pady=5)
        
        # Output directory
        output_frame = tk.LabelFrame(parent, text="Output Directory", padx=10, pady=10)
        output_frame.pack(fill="x", padx=20, pady=10)
        
        self.output_dir_var = tk.StringVar(value=self.config.config.get("output_dir", str(Path.home() / "MusicBeatRecordings")))
        
        dir_frame = tk.Frame(output_frame)
        dir_frame.pack(fill="x", pady=5)
        
        tk.Entry(dir_frame, textvariable=self.output_dir_var, width=40).pack(side="left", padx=(0, 10))
        
        browse_button = tk.Button(
            dir_frame,
            text="Browse",
            command=self.browse_output_dir,
            width=10
        )
        browse_button.pack(side="right")
    
    def create_button(self, parent, text, command):
        """Create button"""
        if HAS_CUSTOMTKINTER:
            return ctk.CTkButton(parent, text=text, command=command)
        else:
            return tk.Button(parent, text=text, command=command)
    
    def change_theme(self, choice):
        """Change theme"""
        if HAS_CUSTOMTKINTER:
            ctk.set_appearance_mode(choice)
            # Don't save yet - wait for save button
    
    def browse_output_dir(self):
        """Browse for output directory"""
        directory = filedialog.askdirectory(
            title="Select Output Directory",
            initialdir=self.output_dir_var.get()
        )
        if directory:
            self.output_dir_var.set(directory)
    
    # Removed test_hotkeys method, no longer used
    
    def save_settings(self):
        """Save settings"""
        try:
            # Get hotkey inputs and validate
            start_stop = self.start_stop_var.get().strip().upper()
            beat = self.beat_var.get().strip().upper()
            exit_key = self.exit_var.get().strip().upper()

            # Non-empty validation
            if not start_stop or not beat or not exit_key:
                self.parent.show_message("Error", "Hotkeys cannot be empty")
                return

            # Disallow combination keys (simple check for '+')
            if '+' in start_stop or '+' in beat or '+' in exit_key:
                self.parent.show_message("Notice", "Current version does not support combination keys (e.g., Ctrl+A). Please use single keys (F2, SPACE, ESC, etc.)")
                return

            # Update hotkeys
            hotkeys = {
                "start_stop": start_stop,
                "beat": beat,
                "exit": exit_key
            }
            self.config.config["hotkeys"] = hotkeys
            
            # Update theme
            if HAS_CUSTOMTKINTER:
                self.config.config["theme"] = self.theme_var.get()
            
            # Update BPM window
            self.config.config["bpm_window"] = self.bpm_window_var.get()
            
            # Update output directory
            self.config.config["output_dir"] = self.output_dir_var.get()
            
            # Save configuration
            if self.config.save_config():
                # Update recorder output directory
                self.parent.recorder.output_dir = Path(self.output_dir_var.get())
                self.parent.recorder.output_dir.mkdir(exist_ok=True, parents=True)
                
                # Try to restart hotkeys dynamically
                if self.parent.restart_hotkeys():
                    self.parent.show_message("Success", "Settings saved, hotkeys applied immediately.")
                else:
                    self.parent.show_message("Success", "Settings saved. However, due to limitations of the current keyboard library, hotkeys may require a restart to take full effect.")
                
                # Close window
                self.on_closing()
            else:
                self.parent.show_message("Error", "Failed to save config file. Please check permissions.")
            
        except Exception as e:
            self.parent.show_message("Error", f"An error occurred while saving settings: {e}")
    
    def on_closing(self):
        """Close settings window"""
        self.window.destroy()

# ============================================
# Launch Application
# ============================================
def main():
    """Main function"""
    print("🎵 UTC Time Recorder - Modern UI Version")
    print("=" * 60)
    
    # Check required libraries
    if not HAS_TKINTER:
        print("❌ Error: Tkinter installation required")
        print("Ubuntu/Debian: sudo apt-get install python3-tk")
        print("macOS: brew install python-tk")
        print("Windows: Usually included with Python installation")
        return
    
    # If customtkinter not available, use standard tkinter
    if not HAS_CUSTOMTKINTER:
        print("⚠️  Recommended to install customtkinter for better UI experience")
        print("Install command: pip install customtkinter")
    
    # Check keyboard library
    if not KEYBOARD_LIB:
        print("⚠️  No keyboard library detected, hotkey functionality will be unavailable")
        print("Recommended installation: pip install pynput")
        print("Alternative installation: pip install keyboard")
    
    # Launch UI
    app = MusicBeatRecorderUI()
    app.run()

if __name__ == "__main__":
    main()