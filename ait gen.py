import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from tkinter import filedialog
import sqlite3
import datetime
import csv
import json
import os
import sys
from difflib import SequenceMatcher
from pathlib import Path
from tkcalendar import DateEntry
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

# --- Working Directory Setup ---
def setup_working_directory():
    """
    Set the working directory to the folder containing this script.
    This allows the program to work on different devices and operating systems.
    """
    try:
        # Get the directory of the current script
        script_dir = Path(__file__).parent.resolve()
        os.chdir(script_dir)
        return str(script_dir)
    except Exception as e:
        print(f"Warning: Could not set working directory: {e}")
        return os.getcwd()

# Call this at startup
WORKING_DIR = setup_working_directory()

# --- Version Management ---
def get_app_version():
    """Load version from VERSION file."""
    try:
        version_file = os.path.join(WORKING_DIR, "VERSION")
        if os.path.exists(version_file):
            with open(version_file, 'r') as f:
                return f.read().strip()
    except Exception as e:
        print(f"Warning: Could not load version: {e}")
    return "1.0"

APP_VERSION = get_app_version()

# --- Window Centering Utility ---
def center_window(window, parent=None):
    """Center a window on the screen or on the parent window."""
    window.update_idletasks()
    if parent:
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (window.winfo_width() // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (window.winfo_height() // 2)
    else:
        x = (window.winfo_screenwidth() // 2) - (window.winfo_width() // 2)
        y = (window.winfo_screenheight() // 2) - (window.winfo_height() // 2)
    window.geometry(f"+{x}+{y}")

# --- Window Management ---
open_windows = {}  # Track open pop-up windows by name

def register_window(window_name, window):
    """Register an open window and clean it up when it closes."""
    if window_name in open_windows and open_windows[window_name].winfo_exists():
        # Window already open, bring it to front
        open_windows[window_name].lift()
        open_windows[window_name].focus()
        return False  # Signal that a new window was not created

    # Register the new window
    open_windows[window_name] = window

    def on_window_close():
        if window_name in open_windows:
            del open_windows[window_name]
        window.destroy()

    window.protocol("WM_DELETE_WINDOW", on_window_close)
    return True  # Signal that the window was created

# --- Config File Management ---
def get_config_path():
    """Get the path to the user's config file in Documents (cross-platform)."""
    try:
        # Cross-platform way to get Documents folder
        home = Path.home()
        docs_path = home / "Documents"
        docs_path.mkdir(exist_ok=True)
        return str(docs_path / "AIT_Generator_Config.json")
    except Exception as e:
        print(f"Warning: Could not determine Documents path: {e}")
        return None

def get_default_database_path():
    """Get the default database path in AppData/Local for better permissions on work machines."""
    try:
        # Use AppData/Local which typically has write permissions on work laptops
        home = Path.home()
        app_data = home / "AppData" / "Local" / "UC_AIT_Generator"
        app_data.mkdir(parents=True, exist_ok=True)
        return str(app_data / "UC_Allergy_AIT.db")
    except Exception:
        # Fallback to working directory if AppData not accessible
        return os.path.join(WORKING_DIR, "UC_Allergy_AIT.db")

def load_config():
    """Load config from Documents folder. Returns dict with defaults if not found."""
    config_path = get_config_path()
    default_db_path = get_default_database_path()

    if not config_path:
        return {
            "database_path": default_db_path,
            "last_save_directory": WORKING_DIR,
            "allergen_overrides": {}
        }

    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                # Validate database path exists; use default if not
                db_path = config.get("database_path", "")
                if not db_path or not os.path.exists(os.path.dirname(db_path)):
                    config["database_path"] = default_db_path
                if not os.path.exists(config.get("last_save_directory", "")):
                    config["last_save_directory"] = WORKING_DIR
                if not isinstance(config.get("allergen_overrides"), dict):
                    config["allergen_overrides"] = {}
                return config
        except Exception as e:
            print(f"Warning: Could not load config: {e}")
            return {
                "database_path": default_db_path,
                "last_save_directory": WORKING_DIR,
                "allergen_overrides": {}
            }
    else:
        # First launch - return defaults with AppData path
        return {
            "database_path": default_db_path,
            "last_save_directory": WORKING_DIR,
            "allergen_overrides": {}
        }

def save_config(config):
    """Save config to Documents folder."""
    config_path = get_config_path()
    if not config_path:
        return False
    
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"Warning: Could not save config: {e}")
        return False


def apply_allergen_overrides(default_allergens, config):
    """Apply per-allergen overrides from config to default allergen data."""
    overrides = config.get("allergen_overrides", {}) if isinstance(config, dict) else {}
    if not isinstance(overrides, dict):
        overrides = {}

    merged = []
    for allergen in default_allergens:
        item = {
            "name": allergen["name"],
            "group": allergen["group"],
            "min_volume": float(allergen["min_volume"]),
            "max_volume": float(allergen["max_volume"]),
            "incompatible_groups": list(allergen.get("incompatible_groups", []))
        }
        override = overrides.get(allergen["name"], {})
        if isinstance(override, dict):
            if isinstance(override.get("min_volume"), (int, float)):
                item["min_volume"] = float(override["min_volume"])
            if isinstance(override.get("max_volume"), (int, float)):
                item["max_volume"] = float(override["max_volume"])
            if isinstance(override.get("incompatible_groups"), list):
                item["incompatible_groups"] = [
                    str(value).strip() for value in override["incompatible_groups"] if str(value).strip()
                ]
        merged.append(item)

    return merged


def build_allergen_overrides(current_allergens, default_allergens):
    """Create a compact overrides dict for allergens that differ from defaults."""
    defaults_by_name = {
        allergen["name"]: allergen for allergen in default_allergens
    }
    overrides = {}
    for allergen in current_allergens:
        name = allergen["name"]
        default = defaults_by_name.get(name)
        if not default:
            continue

        override = {}
        if float(allergen.get("min_volume", 0)) != float(default.get("min_volume", 0)):
            override["min_volume"] = float(allergen.get("min_volume", 0))
        if float(allergen.get("max_volume", 0)) != float(default.get("max_volume", 0)):
            override["max_volume"] = float(allergen.get("max_volume", 0))

        current_incompat = sorted(set(allergen.get("incompatible_groups", [])))
        default_incompat = sorted(set(default.get("incompatible_groups", [])))
        if current_incompat != default_incompat:
            override["incompatible_groups"] = current_incompat

        if override:
            overrides[name] = override

    return overrides

# Load config at startup
CURRENT_CONFIG = load_config()
DB_FILE = CURRENT_CONFIG.get("database_path", os.path.join(WORKING_DIR, "UC_Allergy_AIT.db"))

def handle_first_launch():
    """Check if database path is valid; if not, prompt user to select/create one."""
    global DB_FILE, CURRENT_CONFIG

    db_path = CURRENT_CONFIG.get("database_path")

    # Check if the database path is valid (parent directory exists and path is set)
    if not db_path or not os.path.exists(os.path.dirname(db_path)):
        # Need user input - create a minimal window for the dialog
        temp_root = tk.Tk()
        temp_root.withdraw()  # Hide the temporary window

        # Create custom dialog with clear button labels
        choice_window = tk.Toplevel(temp_root)
        choice_window.title("Database Setup")
        choice_window.geometry("400x150")
        choice_window.resizable(False, False)
        center_window(choice_window, temp_root)

        ttk.Label(choice_window, text="Select an option:", font=('Segoe UI', 11, 'bold')).pack(pady=15)

        result = {"value": None}

        def select_existing():
            result["value"] = True
            choice_window.destroy()

        def create_new():
            result["value"] = False
            choice_window.destroy()

        button_frame = ttk.Frame(choice_window)
        button_frame.pack(pady=10)

        ttk.Button(button_frame, text="📂 Select Existing Database", command=select_existing, width=25).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="➕ Create New Database", command=create_new, width=25).pack(side=tk.LEFT, padx=5)

        choice_window.wait_window()

        if result["value"] is True:  # User wants to select existing
            db_file = filedialog.askopenfilename(
                title="Select Database File",
                filetypes=[("Database files", "*.db"), ("All files", "*.*")],
                initialdir=os.path.expanduser("~")
            )
            if db_file:
                DB_FILE = db_file
                CURRENT_CONFIG['database_path'] = db_file
                save_config(CURRENT_CONFIG)
        elif result["value"] is False:  # User wants to create new
            db_file = filedialog.asksaveasfilename(
                title="Create New Database",
                defaultextension=".db",
                filetypes=[("Database files", "*.db"), ("All files", "*.*")],
                initialdir=os.path.expanduser("~"),
                initialfile="UC_Allergy_AIT.db"
            )
            if db_file:
                DB_FILE = db_file
                CURRENT_CONFIG['database_path'] = db_file
                save_config(CURRENT_CONFIG)

        temp_root.destroy()

# --- Allergen Data ---
DEFAULT_ALLERGENS = [
    # Mold Group
    {"name": "Aspergillus", "group": "Mold", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": ["Tree", "Grass", "Weed", "Other"]},
    {"name": "Alternaria", "group": "Mold", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": ["Tree", "Grass", "Weed", "Other"]},
    {"name": "Cladosporium", "group": "Mold", "min_volume": 1.0, "max_volume": 1.0, "incompatible_groups": ["Tree", "Grass", "Weed", "Other"]},
    {"name": "Penicillium", "group": "Mold", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": ["Tree", "Grass", "Weed", "Other"]},

    # Tree Group
    {"name": "Ash", "group": "Tree", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": ["Mold", "Amer. Cockroach", "Ger. Cockroach"]},
    {"name": "Birch (Oak)", "group": "Tree", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": ["Mold", "Amer. Cockroach", "Ger. Cockroach"]},
    {"name": "Cedar", "group": "Tree", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": ["Mold", "Amer. Cockroach", "Ger. Cockroach"]},
    {"name": "Elm", "group": "Tree", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": ["Mold", "Amer. Cockroach", "Ger. Cockroach"]},
    {"name": "Hackberry (Elm)", "group": "Tree", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": ["Mold", "Amer. Cockroach", "Ger. Cockroach"]},
    {"name": "Maple", "group": "Tree", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": ["Mold", "Amer. Cockroach", "Ger. Cockroach"]},
    {"name": "Sycamore", "group": "Tree", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": ["Mold", "Amer. Cockroach", "Ger. Cockroach"]},
    {"name": "Walnut (Pecan)", "group": "Tree", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": ["Mold", "Amer. Cockroach", "Ger. Cockroach"]},
    {"name": "Willow (Cottonwood)", "group": "Tree", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": ["Mold", "Amer. Cockroach", "Ger. Cockroach"]},
    {"name": "Mulberry", "group": "Tree", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": ["Mold", "Amer. Cockroach", "Ger. Cockroach"]},

    # Grass Group
    {"name": "Timothy", "group": "Grass", "min_volume": 0.1, "max_volume": 0.4, "incompatible_groups": ["Mold", "Amer. Cockroach", "Ger. Cockroach"]},
    {"name": "Johnson", "group": "Grass", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": ["Mold", "Amer. Cockroach", "Ger. Cockroach"]},
    {"name": "Bermuda", "group": "Grass", "min_volume": 0.3, "max_volume": 1.0, "incompatible_groups": ["Mold", "Amer. Cockroach", "Ger. Cockroach"]},

    # Weed Group
    {"name": "Cocklebur", "group": "Weed", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": ["Mold", "Amer. Cockroach", "Ger. Cockroach"]},
    {"name": "Yellow Dock (Sheep Sorrel)", "group": "Weed", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": ["Mold", "Amer. Cockroach", "Ger. Cockroach"]},
    {"name": "Kochia (Burning Bush)", "group": "Weed", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": ["Mold", "Amer. Cockroach", "Ger. Cockroach"]},
    {"name": "Lamb's Quarter", "group": "Weed", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": ["Mold", "Amer. Cockroach", "Ger. Cockroach"]},
    {"name": "Mugwort", "group": "Weed", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": ["Mold", "Amer. Cockroach", "Ger. Cockroach"]},
    {"name": "Pigweed", "group": "Weed", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": ["Mold", "Amer. Cockroach", "Ger. Cockroach"]},
    {"name": "English Plantain", "group": "Weed", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": ["Mold", "Amer. Cockroach", "Ger. Cockroach"]},
    {"name": "Russian Thistle", "group": "Weed", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": ["Mold", "Amer. Cockroach", "Ger. Cockroach"]},
    {"name": "Ragweed", "group": "Weed", "min_volume": 0.3, "max_volume": 0.6, "incompatible_groups": ["Mold", "Amer. Cockroach", "Ger. Cockroach"]},

    # Other Group - Animals
    {"name": "Cat", "group": "Other", "min_volume": 1.0, "max_volume": 4.0, "incompatible_groups": []},
    {"name": "Dog - UF", "group": "Other", "min_volume": 1.0, "max_volume": 1.0, "incompatible_groups": ["Mold"]},
    {"name": "Dog - Epithelium", "group": "Other", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": ["Mold"]},
    {"name": "Mouse", "group": "Other", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": []},
    {"name": "Rat", "group": "Other", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": []},
    {"name": "Horse", "group": "Other", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": []},
    {"name": "Amer. Cockroach", "group": "Other", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": ["Tree", "Grass", "Weed"]},
    {"name": "Ger. Cockroach", "group": "Other", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": ["Tree", "Grass", "Weed"]},
    {"name": "Dust Mite Mix", "group": "Other", "min_volume": 0.5, "max_volume": 2.0, "incompatible_groups": []},

     # Venom Group
    {"name": "Honey Bee", "group": "Venom", "min_volume": 1.0, "max_volume": 1.0, "incompatible_groups": []},
    {"name": "Yellow Jacket", "group": "Venom", "min_volume": 1.0, "max_volume": 1.0, "incompatible_groups": []},
    {"name": "Yellow Faced Hornet", "group": "Venom", "min_volume": 1.0, "max_volume": 1.0, "incompatible_groups": []},
    {"name": "White Faced Hornet", "group": "Venom", "min_volume": 1.0, "max_volume": 1.0, "incompatible_groups": []},
    {"name": "Wasp", "group": "Venom", "min_volume": 1.0, "max_volume": 1.0, "incompatible_groups": []},
]

ALLERGENS = apply_allergen_overrides(DEFAULT_ALLERGENS, CURRENT_CONFIG)

# Define allergen group order for display
GROUP_ORDER = ["Mold", "Tree", "Grass", "Weed", "Other"]

# Define quick-set volumes for common allergens in Edit Volumes dialog
ALLERGEN_QUICK_VOLUMES = {
    "Cat": [1.0, 2.0, 3.0, 4.0],
    "Dust Mite Mix": [0.5, 1.0, 1.5, 2.0],
    "Ragweed": [0.3, 0.4, 0.5, 0.6],
    "Bermuda": [0.3, 0.5, 1.0],
    "Timothy": [0.1, 0.2, 0.3, 0.4],
    # Default for all other allergens
    "_default": [0.5, 1.0]
}

def sort_allergens_by_group(allergen_names):
    """Sort allergen names by group priority (Mold, Tree, Grass, Weed, Other), then alphabetically within each group."""
    allergen_map = {a["name"]: a["group"] for a in ALLERGENS}

    def get_sort_key(allergen_name):
        group = allergen_map.get(allergen_name, "Other")
        group_priority = GROUP_ORDER.index(group) if group in GROUP_ORDER else len(GROUP_ORDER)
        return (group_priority, allergen_name)

    return sorted(allergen_names, key=get_sort_key)

# Stock-only items (do not appear in main allergen selection UI)
STOCK_ONLY_EXTRACTS = [
    "Normal Saline with Human Serum Albumin - Silver Top",
    "Normal Saline with Human Serum Albumin - Green Top",
    "Normal Saline with Human Serum Albumin - Blue Top",
    "Normal Saline with Human Serum Albumin - Yellow Top",
    "Red Top - empty 5 mL",
    "HSA Diluent",
]


def get_stock_allergen_names():
    """Return allergen names plus stock-only items for stock management."""
    return sorted([a["name"] for a in ALLERGENS] + STOCK_ONLY_EXTRACTS)

# --- Global Variables for Prescription Storage ---
last_prescription_data = {}
last_vials = []
treatment_type_var = None  # Will be initialized in UI setup
allow_fourth_vial_var = None  # Will be initialized in UI setup
prescriber_var = None  # Will be initialized in UI setup
mix_preparer_var = None  # Will be initialized in UI setup
last_compounding_log_id = None  # Will store the compounding log ID for PDF export
last_save_directory = CURRENT_CONFIG.get("last_save_directory", WORKING_DIR)  # Remember the last save directory for file dialogs
prescription_generated = False  # Track if current displayed prescription matches current selections

# --- Avery 45160 Label Specifications ---
# Avery 45160 Address Labels: 30 labels per sheet (6 rows × 5 columns)
# Each label: 1 inch height × 2.625 inches width
LABEL_AVERY_SPECS = {
    'page_width': 8.5,  # inches
    'page_height': 11,  # inches
    'top_margin': 0.5,  # inches (36 pt)
    'left_margin': 0.1875,  # inches (13.5 pt)
    'col_gap': 0.1215,  # inches (8.75 pt)
    'label_height': 1.0,  # inches
    'label_width': 2.625,  # inches
    'cols': 3,  # columns per row
    'rows': 10,  # rows per page
}

# --- Database Setup ---
# DB_FILE is now loaded from config in load_config() above

def init_database():
    """Initialize the SQLite database with the patients table."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_name TEXT NOT NULL,
                dob TEXT NOT NULL,
                mrn TEXT UNIQUE NOT NULL,
                address TEXT,
                city TEXT,
                state TEXT,
                zip_code TEXT,
                phone TEXT,
                allergens TEXT,
                treatment_type TEXT DEFAULT 'New Start',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Add missing columns if they don't exist (for existing databases)
        cursor.execute("PRAGMA table_info(patients)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'treatment_type' not in columns:
            cursor.execute('ALTER TABLE patients ADD COLUMN treatment_type TEXT DEFAULT "New Start"')
        if 'zip_code' not in columns:
            cursor.execute('ALTER TABLE patients ADD COLUMN zip_code TEXT')
        if 'last_prescription_json' not in columns:
            cursor.execute('ALTER TABLE patients ADD COLUMN last_prescription_json TEXT')
        
        # Create stock_extracts table for inventory management
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stock_extracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                allergen_name TEXT NOT NULL,
                concentration TEXT,
                manufacturer_item TEXT,
                lot_number TEXT NOT NULL,
                expiration_date TEXT,
                vial_amount TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create compounding_logs table to track vial mixes
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS compounding_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER,
                patient_name TEXT,
                dob TEXT,
                vial_type TEXT,
                treatment_type TEXT,
                mix_date TEXT,
                lot_number TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(patient_id) REFERENCES patients(id)
            )
        ''')
        
        # Create compounding_log_items table to track allergen usage per vial
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS compounding_log_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                compounding_log_id INTEGER NOT NULL,
                vial_letter TEXT,
                allergen_name TEXT,
                volume_used REAL,
                stock_extract_id INTEGER,
                concentration TEXT,
                manufacturer_item TEXT,
                lot_number TEXT,
                expiration_date TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(compounding_log_id) REFERENCES compounding_logs(id),
                FOREIGN KEY(stock_extract_id) REFERENCES stock_extracts(id)
            )
        ''')

        # Create staff_members table for managing prescribers and preparers
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS staff_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                role TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create patient_prescriptions table to store prescriptions for each patient (can have multiple per patient, one per vial type)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS patient_prescriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL,
                vial_type TEXT NOT NULL,
                treatment_type TEXT,
                max_volume REAL DEFAULT 5.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(patient_id, vial_type),
                FOREIGN KEY(patient_id) REFERENCES patients(id)
            )
        ''')

        # CRITICAL: Verify and fix database schema
        try:
            print("Verifying patient_prescriptions schema...")
            cursor.execute("PRAGMA foreign_keys=OFF")

            # Check if we need to migrate by looking at the actual constraint
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='patient_prescriptions'")
            table_sql_result = cursor.fetchone()

            needs_migration = False

            if table_sql_result and table_sql_result[0]:
                table_sql = table_sql_result[0]
                # Check for old constraint pattern: patient_id with UNIQUE (not compound)
                # Old pattern: "patient_id INTEGER UNIQUE" or similar
                # New pattern: "UNIQUE(patient_id, vial_type)" or "UNIQUE(patient_id,vial_type)"
                has_old_constraint = ("UNIQUE NOT NULL" in table_sql or "UNIQUE," in table_sql) and "UNIQUE(patient_id, vial_type)" not in table_sql and "UNIQUE(patient_id,vial_type)" not in table_sql

                if has_old_constraint:
                    print("  OLD UNIQUE constraint detected - MIGRATING SCHEMA")
                    needs_migration = True
                else:
                    print("  Schema looks correct")
            else:
                print("  Could not check schema (table may not exist yet)")
                needs_migration = False

            if needs_migration:
                print("Attempting to migrate patient_prescriptions table...")

                # Back up existing data
                cursor.execute("SELECT COUNT(*) FROM patient_prescriptions")
                count = cursor.fetchone()[0]
                print(f"  Found {count} existing records")

                if count > 0:
                    # Create backup
                    cursor.execute("ALTER TABLE patient_prescriptions RENAME TO patient_prescriptions_backup")
                    print("  Backed up old table")

                    # Create new table with correct schema
                    cursor.execute('''
                        CREATE TABLE patient_prescriptions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            patient_id INTEGER NOT NULL,
                            vial_type TEXT NOT NULL,
                            treatment_type TEXT,
                            max_volume REAL DEFAULT 5.0,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(patient_id, vial_type),
                            FOREIGN KEY(patient_id) REFERENCES patients(id)
                        )
                    ''')

                    # Copy data with proper vial_type assignment
                    cursor.execute('''
                        INSERT INTO patient_prescriptions (id, patient_id, vial_type, treatment_type, max_volume, created_at, updated_at)
                        SELECT id, patient_id, COALESCE(vial_type, 'Environmental'), treatment_type, COALESCE(max_volume, 5.0), created_at, updated_at
                        FROM patient_prescriptions_backup
                    ''')

                    cursor.execute("DROP TABLE patient_prescriptions_backup")
                    print("  Migration complete - data preserved")
                else:
                    # No data, just recreate
                    cursor.execute("DROP TABLE IF EXISTS patient_prescriptions")
                    cursor.execute('''
                        CREATE TABLE patient_prescriptions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            patient_id INTEGER NOT NULL,
                            vial_type TEXT NOT NULL,
                            treatment_type TEXT,
                            max_volume REAL DEFAULT 5.0,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(patient_id, vial_type),
                            FOREIGN KEY(patient_id) REFERENCES patients(id)
                        )
                    ''')
                    print("  Created new empty table with correct schema")

            cursor.execute("PRAGMA foreign_keys=ON")

        except Exception as e:
            print(f"ERROR during schema verification: {e}")
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
            except:
                pass


        # Create patient_prescription_vials table to store vial compositions
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS patient_prescription_vials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prescription_id INTEGER NOT NULL,
                vial_letter TEXT,
                allergen_name TEXT,
                volume REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(prescription_id) REFERENCES patient_prescriptions(id)
            )
        ''')

        # Insert default staff members if they don't exist
        try:
            cursor.execute("INSERT OR IGNORE INTO staff_members (name, role) VALUES (?, ?)",
                          ("Yashu Dhamija MD", "Prescriber"))
            cursor.execute("INSERT OR IGNORE INTO staff_members (name, role) VALUES (?, ?)",
                          ("Joshua Bernstein MD", "Prescriber"))
            cursor.execute("INSERT OR IGNORE INTO staff_members (name, role) VALUES (?, ?)",
                          ("Elaine Sturtevant RN", "Preparer"))
        except Exception:
            pass

        conn.commit()
        conn.close()
    except Exception as e:
        messagebox.showerror("Database Error", f"Failed to initialize database: {e}")


def check_database_connection():
    """Check if database connection is working. Returns (bool, str) - (is_connected, status_message)"""
    try:
        conn = sqlite3.connect(DB_FILE, timeout=5)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        return True, f"[OK] Connected: {os.path.basename(DB_FILE)}"
    except sqlite3.OperationalError as e:
        if "database is locked" in str(e).lower():
            return False, f"[WARN] Database locked (check permissions): {os.path.basename(DB_FILE)}"
        elif "unable to open database file" in str(e).lower():
            return False, f"[ERROR] Cannot access: {os.path.basename(DB_FILE)}"
        else:
            return False, f"[ERROR] Connection error: {str(e)[:50]}"
    except Exception as e:
        return False, f"[ERROR] Error: {str(e)[:50]}"


def import_stock_csv(csv_file_path):
    """Import stock extract data from CSV with manual allergen matching."""
    try:
        with open(csv_file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        if not rows:
            messagebox.showwarning("Import", "CSV file is empty.")
            return None
        
        print(f"CSV Columns Found: {list(rows[0].keys())}")
        
        item_col = None
        for col in rows[0].keys():
            if col.lower().strip().startswith("item"):
                item_col = col
                break
        
        if not item_col:
            messagebox.showerror("Error", f"CSV file does not have an 'Item' column.\nFound columns: {', '.join(rows[0].keys())}")
            return None
        
        def find_column(row, *possible_names):
            for name in possible_names:
                if name in row:
                    return row[name]
            return ""
        
        allergen_names = get_stock_allergen_names()
        allergen_options = ["— None —"] + allergen_names
        normalized_allergen_names = [(name, "".join(ch.lower() for ch in name if ch.isalnum() or ch.isspace()).strip())
                                     for name in allergen_names]

        def fuzzy_match_allergen_name(csv_name):
            norm_csv = "".join(ch.lower() for ch in csv_name if ch.isalnum() or ch.isspace()).strip()
            if not norm_csv:
                return "", 0.0
            best_name = ""
            best_score = 0.0
            for name, norm_name in normalized_allergen_names:
                score = SequenceMatcher(None, norm_csv, norm_name).ratio()
                if score > best_score:
                    best_score = score
                    best_name = name
            return best_name, best_score
        mapping_window = tk.Toplevel(root)
        mapping_window.title("Manual Stock Import Matching")
        mapping_window.geometry("1000x700")
        center_window(mapping_window, root)

        instruction_label = tk.Label(mapping_window, text="Select the matching allergen from the dropdown for each CSV item, then click Import to add it to the database.",
                                     wraplength=900, justify=tk.LEFT, bg="#f0f2f5", fg="#2c3e50")
        instruction_label.pack(fill=tk.X, padx=10, pady=10)
        
        canvas = tk.Canvas(mapping_window, bg="#ffffff", highlightthickness=0)
        scrollbar = ttk.Scrollbar(mapping_window, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        selections = []
        row_count = 0
        
        for idx, row in enumerate(rows):
            csv_item = row.get(item_col, "").strip()
            if not csv_item:
                continue
            
            row_count += 1
            row_frame = ttk.LabelFrame(scrollable_frame, text=f"Item {row_count}: {csv_item}", padding=10)
            row_frame.pack(fill=tk.X, padx=0, pady=5)
            
            concentration = find_column(row, "Concentration", "concentration", "Conc")
            manuf = find_column(row, "Manfu Item", "Manfu Item ", "Manufacturer Item", "Mfr Item")
            lot = find_column(row, "LOT", "lot", "Lot", "Lot Number")
            expiration = find_column(row, "Expiration", "expiration", "Exp Date", "Exp")
            vial_amt = find_column(row, "Vial Amt", "Vial Amt ", "Vial Amount", "Amount")
            
            data_text = f"Concentration: {concentration.strip()} | Manuf: {manuf.strip()} | Lot: {lot.strip()} | Exp: {expiration.strip()} | Amt: {vial_amt.strip()}"
            data_label = tk.Label(row_frame, text=data_text, fg="#666666", font=("Segoe UI", 8), wraplength=900, justify=tk.LEFT)
            data_label.pack(fill=tk.X, pady=(0, 8))
            
            selection_frame = ttk.Frame(row_frame)
            selection_frame.pack(fill=tk.X, pady=5)
            ttk.Label(selection_frame, text="Select Allergen:").pack(side=tk.LEFT, padx=(0, 5))
            
            best_name, best_score = fuzzy_match_allergen_name(csv_item)
            default_value = best_name if best_score >= 0.6 else "— None —"
            var = tk.StringVar(value=default_value)
            combo = ttk.Combobox(selection_frame, textvariable=var, values=allergen_options, state='readonly', width=30)
            combo.pack(side=tk.LEFT, padx=(0, 5), fill=tk.X, expand=True)
            
            selections.append({
                'csv_item': csv_item,
                'var': var,
                'concentration': concentration,
                'manuf': manuf,
                'lot': lot,
                'expiration': expiration,
                'vial_amt': vial_amt
            })
        
        if row_count == 0:
            mapping_window.destroy()
            messagebox.showwarning("Import", f"No valid items found in CSV.\nColumn names in file: {', '.join(rows[0].keys())}")
            return None
        
        button_frame = ttk.Frame(mapping_window)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        def confirm_import():
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            imported_count = 0
            skipped_count = 0
            
            for data in selections:
                csv_item = data['csv_item']
                selected_allergen = data['var'].get().strip()
                
                if not selected_allergen or selected_allergen == "— None —":
                    skipped_count += 1
                    continue
                
                concentration = data['concentration'].strip()
                manufacturer_item = data['manuf'].strip()
                lot_number = data['lot'].strip()
                expiration = data['expiration'].strip()
                vial_amt = data['vial_amt'].strip()
                
                if not lot_number:
                    skipped_count += 1
                    continue
                
                # Insert new stock record
                try:
                    cursor.execute('''
                        INSERT INTO stock_extracts 
                        (allergen_name, concentration, manufacturer_item, lot_number, expiration_date, vial_amount, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, 0)
                    ''', (selected_allergen, concentration, manufacturer_item, lot_number, expiration, vial_amt))
                    imported_count += 1
                except Exception as e:
                    print(f"Error inserting {csv_item}: {e}")
                    skipped_count += 1
            
            conn.commit()
            conn.close()
            
            mapping_window.destroy()
            messagebox.showinfo("Import Complete", f"Imported {imported_count} records.\nSkipped {skipped_count} records.")
        
        import_btn = ttk.Button(button_frame, text="📥 Import Selected", command=confirm_import)
        import_btn.pack(side=tk.LEFT, padx=5)
        
        cancel_btn = ttk.Button(button_frame, text="Cancel", command=mapping_window.destroy)
        cancel_btn.pack(side=tk.LEFT, padx=5)
        
        return None
    
    except Exception as e:
        messagebox.showerror("Error", f"Failed to import CSV: {e}")
        return None


class Vial:
    """Represents a single allergy vial."""

    def __init__(self, label):
        self.label = label
        self.allergens = {}
        self.current_volume = 0.0
        self.custom_max_volume = 5.0  # Default to 5 mL, can be overridden

    def add_allergen(self, allergen_name, volume):
        """Adds an allergen to the vial if compatible and within volume limits."""
        allergen_data = next((a for a in ALLERGENS if a["name"] == allergen_name), None)
        if not allergen_data:
            return False

        if not self.is_compatible(allergen_data):
            return False

        if self.current_volume + volume > self.custom_max_volume:
            return False

        if not (allergen_data["min_volume"] <= volume <= allergen_data["max_volume"]):
            return False

        self.allergens[allergen_name] = volume
        self.current_volume += volume
        return True

    def remaining_volume(self):
        """Calculates the remaining volume in the vial."""
        return self.custom_max_volume - self.current_volume

    def is_compatible(self, allergen_data):
        """Checks if an allergen is compatible with the current vial contents.

        Compatibility is bidirectional:
        1. Check if the allergen is incompatible with any current groups/allergens
        2. Check if any current allergens are incompatible with this allergen
        """
        new_allergen_name = allergen_data["name"]

        current_groups = {a["group"] for a in ALLERGENS if a["name"] in self.allergens}
        for group in current_groups:
            if group in allergen_data["incompatible_groups"]:
                return False

        for name in self.allergens:
            if name in allergen_data["incompatible_groups"]:
                return False

        for allergen_name in self.allergens:
            current_allergen = next((a for a in ALLERGENS if a["name"] == allergen_name), None)
            if current_allergen:
                if allergen_data["group"] in current_allergen["incompatible_groups"]:
                    return False
                if new_allergen_name in current_allergen["incompatible_groups"]:
                    return False

        return True

    def get_contents_string(self):
        """Returns a formatted string of the vial's contents."""
        contents = []
        for allergen, volume in self.allergens.items():
            contents.append(f"  - {allergen}: {volume:.2f} mL")
        contents.append(f"  - Diluent: {self.remaining_volume():.2f} mL")
        return "\n".join(contents)


def open_settings():
    """Open Settings window to change database path."""
    global DB_FILE, CURRENT_CONFIG

    settings_window = tk.Toplevel(root)
    settings_window.title("Settings")
    settings_window.geometry("600x300")
    center_window(settings_window, root)

    # Prevent duplicate windows
    if not register_window("settings", settings_window):
        return

    # Database Path Section
    ttk.Label(settings_window, text="Database File:", font=('Segoe UI', 10, 'bold')).pack(padx=10, pady=(10, 5), anchor="w")
    
    db_frame = ttk.Frame(settings_window)
    db_frame.pack(fill=tk.X, padx=10, pady=5)
    
    db_path_var = tk.StringVar(value=CURRENT_CONFIG.get('database_path', DB_FILE))
    db_path_entry = ttk.Entry(db_frame, textvariable=db_path_var, width=50)
    db_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
    
    def browse_databases():
        """Browse for existing database or location for new one."""
        # Create custom dialog with clear button labels
        choice_window = tk.Toplevel(root)
        choice_window.title("Database Selection")
        choice_window.geometry("400x150")
        choice_window.resizable(False, False)
        center_window(choice_window, root)

        # Center the window
        choice_window.transient(root)
        choice_window.grab_set()

        ttk.Label(choice_window, text="Select an option:", font=('Segoe UI', 11, 'bold')).pack(pady=15)

        result = {"value": None}

        def select_existing():
            result["value"] = True
            choice_window.destroy()

        def create_new():
            result["value"] = False
            choice_window.destroy()

        button_frame = ttk.Frame(choice_window)
        button_frame.pack(pady=10)

        ttk.Button(button_frame, text="📂 Select Existing Database", command=select_existing, width=25).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="➕ Create New Database", command=create_new, width=25).pack(side=tk.LEFT, padx=5)

        choice_window.wait_window()

        if result["value"] is True:
            # Select existing database
            file_path = filedialog.askopenfilename(
                title="Select AIT Database",
                filetypes=[("SQLite Database", "*.db"), ("All Files", "*.*")],
                initialdir=os.path.dirname(CURRENT_CONFIG.get('database_path', DB_FILE))
            )
            if file_path:
                db_path_var.set(file_path)
        elif result["value"] is False:
            # Choose location for new database
            file_path = filedialog.asksaveasfilename(
                title="Create New Database",
                defaultextension=".db",
                filetypes=[("SQLite Database", "*.db"), ("All Files", "*.*")],
                initialdir=os.path.dirname(CURRENT_CONFIG.get('database_path', DB_FILE)),
                initialfile="UC_Allergy_AIT.db"
            )
            if file_path:
                db_path_var.set(file_path)
    
    browse_button = ttk.Button(db_frame, text="Browse", command=browse_databases)
    browse_button.pack(side=tk.LEFT)
    
    ttk.Label(settings_window, text="Current Database:", font=('Segoe UI', 9)).pack(padx=10, pady=(10, 2), anchor="w")
    ttk.Label(settings_window, text=CURRENT_CONFIG.get('database_path', DB_FILE), 
              font=('Segoe UI', 8, 'italic'), foreground='gray').pack(padx=15, pady=(0, 10), anchor="w")
    
    # Buttons
    button_frame = ttk.Frame(settings_window)
    button_frame.pack(fill=tk.X, padx=10, pady=20)
    
    def save_settings():
        """Save settings and restart if database changed."""
        new_db_path = db_path_var.get()
        
        if not new_db_path:
            messagebox.showerror("Error", "Database path cannot be empty")
            return
        
        # Check if path is valid (parent directory exists)
        parent_dir = os.path.dirname(new_db_path)
        if not os.path.exists(parent_dir):
            messagebox.showerror("Error", f"Directory does not exist: {parent_dir}")
            return
        
        CURRENT_CONFIG['database_path'] = new_db_path
        save_config(CURRENT_CONFIG)
        
        if new_db_path != DB_FILE:
            messagebox.showinfo("Success", "Database path updated.\nThe application will restart with the new database.")
            settings_window.destroy()
            # Restart the application
            python = sys.executable
            os.execl(python, python, *sys.argv)
        else:
            messagebox.showinfo("Success", "Settings saved.")
            settings_window.destroy()
    
    save_button = ttk.Button(button_frame, text="Save", command=save_settings)
    save_button.pack(side=tk.LEFT, padx=5)
    
    cancel_button = ttk.Button(button_frame, text="Cancel", command=settings_window.destroy)
    cancel_button.pack(side=tk.LEFT, padx=5)


def open_dose_ranges_window():
    """Open a window to edit allergen dose ranges and compatibility."""
    global ALLERGENS, CURRENT_CONFIG

    dose_window = tk.Toplevel(root)
    dose_window.title("Dose Ranges")
    dose_window.geometry("1000x650")
    center_window(dose_window, root)

    # Prevent duplicate windows
    if not register_window("dose_ranges", dose_window):
        return

    bg_color = BG_COLOR if "BG_COLOR" in globals() else root.cget("bg")
    dose_window.configure(bg=bg_color)

    container = ttk.Frame(dose_window, padding=10)
    container.pack(fill=tk.BOTH, expand=True)

    left_frame = ttk.Frame(container)
    left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

    right_frame = ttk.Frame(container)
    right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

    ttk.Label(left_frame, text="Allergens", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 6))

    tree = ttk.Treeview(left_frame, columns=("Name", "Group", "Min", "Max"), show="headings", height=22)
    tree.heading("Name", text="Name")
    tree.heading("Group", text="Group")
    tree.heading("Min", text="Min (mL)")
    tree.heading("Max", text="Max (mL)")
    tree.column("Name", width=220)
    tree.column("Group", width=120)
    tree.column("Min", width=90)
    tree.column("Max", width=90)

    tree_scroll = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=tree.yview)
    tree.configure(yscroll=tree_scroll.set)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    selected_name_var = tk.StringVar(value="")
    min_var = tk.StringVar()
    max_var = tk.StringVar()

    groups = sorted({a["group"] for a in DEFAULT_ALLERGENS})
    allergen_names = sorted([a["name"] for a in DEFAULT_ALLERGENS])

    ttk.Label(right_frame, text="Selected Allergen", font=("Segoe UI", 10, "bold")).pack(anchor="w")
    selected_label = ttk.Label(right_frame, textvariable=selected_name_var, font=("Segoe UI", 10))
    selected_label.pack(anchor="w", pady=(0, 10))

    range_frame = ttk.Frame(right_frame)
    range_frame.pack(fill=tk.X, pady=(0, 10))
    ttk.Label(range_frame, text="Min Volume (mL):", width=18).grid(row=0, column=0, sticky="w")
    min_entry = ttk.Entry(range_frame, textvariable=min_var, width=10)
    min_entry.grid(row=0, column=1, sticky="w", padx=(4, 12))
    ttk.Label(range_frame, text="Max Volume (mL):", width=18).grid(row=1, column=0, sticky="w")
    max_entry = ttk.Entry(range_frame, textvariable=max_var, width=10)
    max_entry.grid(row=1, column=1, sticky="w", padx=(4, 12))

    ttk.Label(right_frame, text="Incompatible Groups", font=("Segoe UI", 10, "bold")).pack(anchor="w")
    group_list_frame = ttk.Frame(right_frame)
    group_list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
    incompatible_groups_list = tk.Listbox(group_list_frame, selectmode=tk.MULTIPLE, exportselection=False, height=6)
    for group in groups:
        incompatible_groups_list.insert(tk.END, group)
    group_scroll = ttk.Scrollbar(group_list_frame, orient=tk.VERTICAL, command=incompatible_groups_list.yview)
    incompatible_groups_list.configure(yscrollcommand=group_scroll.set)
    incompatible_groups_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    group_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    ttk.Label(right_frame, text="Incompatible Allergens", font=("Segoe UI", 10, "bold")).pack(anchor="w")
    allergen_list_frame = ttk.Frame(right_frame)
    allergen_list_frame.pack(fill=tk.BOTH, expand=True)
    incompatible_allergens_list = tk.Listbox(allergen_list_frame, selectmode=tk.MULTIPLE, exportselection=False, height=10)
    for name in allergen_names:
        incompatible_allergens_list.insert(tk.END, name)
    allergen_scroll = ttk.Scrollbar(allergen_list_frame, orient=tk.VERTICAL, command=incompatible_allergens_list.yview)
    incompatible_allergens_list.configure(yscrollcommand=allergen_scroll.set)
    incompatible_allergens_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    allergen_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def refresh_tree():
        for item in tree.get_children():
            tree.delete(item)
        for allergen in sorted(ALLERGENS, key=lambda a: (a["group"], a["name"])):
            tree.insert(
                "",
                tk.END,
                values=(
                    allergen["name"],
                    allergen["group"],
                    f"{float(allergen['min_volume']):.2f}",
                    f"{float(allergen['max_volume']):.2f}"
                )
            )

    def load_allergen_details(allergen_name):
        selected_name_var.set(allergen_name)
        allergen = next((a for a in ALLERGENS if a["name"] == allergen_name), None)
        if not allergen:
            min_var.set("")
            max_var.set("")
            incompatible_groups_list.selection_clear(0, tk.END)
            incompatible_allergens_list.selection_clear(0, tk.END)
            return

        min_var.set(f"{float(allergen['min_volume']):.2f}")
        max_var.set(f"{float(allergen['max_volume']):.2f}")

        incompat = set(allergen.get("incompatible_groups", []))
        incompatible_groups_list.selection_clear(0, tk.END)
        for idx, group in enumerate(groups):
            if group in incompat:
                incompatible_groups_list.selection_set(idx)

        incompatible_allergens_list.selection_clear(0, tk.END)
        for idx, name in enumerate(allergen_names):
            if name in incompat:
                incompatible_allergens_list.selection_set(idx)

    def get_selected_listbox_values(listbox, values):
        return [values[idx] for idx in listbox.curselection()]

    def persist_overrides():
        CURRENT_CONFIG["allergen_overrides"] = build_allergen_overrides(ALLERGENS, DEFAULT_ALLERGENS)
        save_config(CURRENT_CONFIG)

    def save_selected():
        selected = tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Select an allergen to edit.")
            return

        allergen_name = tree.item(selected[0])["values"][0]
        try:
            min_value = float(min_var.get())
            max_value = float(max_var.get())
        except ValueError:
            messagebox.showerror("Error", "Min and max volumes must be numeric.")
            return

        if min_value < 0 or max_value <= 0 or min_value > max_value:
            messagebox.showerror("Error", "Min and max volumes must be valid and min <= max.")
            return
        if max_value > 5.0:
            if not messagebox.askyesno("Confirm", "Max volume exceeds 5.00 mL. Save anyway?"):
                return

        selected_groups = get_selected_listbox_values(incompatible_groups_list, groups)
        selected_allergens = get_selected_listbox_values(incompatible_allergens_list, allergen_names)
        incompatible = sorted(set(selected_groups + selected_allergens))
        if allergen_name in incompatible:
            incompatible.remove(allergen_name)

        for allergen in ALLERGENS:
            if allergen["name"] == allergen_name:
                allergen["min_volume"] = float(min_value)
                allergen["max_volume"] = float(max_value)
                allergen["incompatible_groups"] = incompatible
                break

        tree.item(selected[0], values=(
            allergen_name,
            next((a["group"] for a in ALLERGENS if a["name"] == allergen_name), ""),
            f"{min_value:.2f}",
            f"{max_value:.2f}"
        ))
        persist_overrides()
        show_toast("Dose ranges saved")

    def reset_selected():
        selected = tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Select an allergen to reset.")
            return
        allergen_name = tree.item(selected[0])["values"][0]
        default = next((a for a in DEFAULT_ALLERGENS if a["name"] == allergen_name), None)
        if not default:
            return
        for allergen in ALLERGENS:
            if allergen["name"] == allergen_name:
                allergen["min_volume"] = float(default["min_volume"])
                allergen["max_volume"] = float(default["max_volume"])
                allergen["incompatible_groups"] = list(default.get("incompatible_groups", []))
                break
        load_allergen_details(allergen_name)
        refresh_tree()
        persist_overrides()
        show_toast("Dose ranges reset")

    def reset_all():
        global ALLERGENS
        if not messagebox.askyesno("Confirm", "Reset all dose ranges and compatibility to defaults?"):
            return
        ALLERGENS = apply_allergen_overrides(DEFAULT_ALLERGENS, {"allergen_overrides": {}})
        CURRENT_CONFIG["allergen_overrides"] = {}
        save_config(CURRENT_CONFIG)
        refresh_tree()
        if tree.get_children():
            first_item = tree.get_children()[0]
            tree.selection_set(first_item)
            load_allergen_details(tree.item(first_item)["values"][0])
        show_toast("All dose ranges reset")

    def on_tree_select(event):
        selected = tree.selection()
        if selected:
            allergen_name = tree.item(selected[0])["values"][0]
            load_allergen_details(allergen_name)

    tree.bind("<<TreeviewSelect>>", on_tree_select)

    button_frame = ttk.Frame(right_frame)
    button_frame.pack(fill=tk.X, pady=(10, 0))
    ttk.Button(button_frame, text="Save", command=save_selected).pack(side=tk.LEFT, padx=5)
    ttk.Button(button_frame, text="Reset Selected", command=reset_selected).pack(side=tk.LEFT, padx=5)
    ttk.Button(button_frame, text="Reset All", command=reset_all).pack(side=tk.LEFT, padx=5)
    ttk.Button(button_frame, text="Close", command=dose_window.destroy).pack(side=tk.RIGHT, padx=5)

    refresh_tree()
    if tree.get_children():
        first_item = tree.get_children()[0]
        tree.selection_set(first_item)
        load_allergen_details(tree.item(first_item)["values"][0])


def show_toast(message, duration=3000, link_text=None, link_action=None):
    """Displays a toast notification in the bottom-right corner of the window.

    Args:
        message: The main message text
        duration: How long to show (milliseconds)
        link_text: Optional text for a clickable link
        link_action: Optional callback function for when the link is clicked
    """
    toast = tk.Toplevel(root)
    toast.wm_overrideredirect(True)
    toast.attributes('-topmost', True)

    # Style the toast
    toast.configure(bg='#333333')

    # Create frame for content
    content_frame = tk.Frame(toast, bg='#333333')
    content_frame.pack(padx=15, pady=10)

    # Main message label
    label = tk.Label(content_frame, text=message, bg='#333333', fg='white',
                    font=('Segoe UI', 9))
    label.pack(anchor='w')

    # Optional clickable link
    if link_text and link_action:
        link = tk.Label(content_frame, text=link_text, bg='#333333', fg='#4da6ff',
                       font=('Segoe UI', 9, 'underline'), cursor='hand2')
        link.pack(anchor='w', pady=(5, 0))
        link.bind('<Button-1>', lambda e: link_action())

    # Get window dimensions to position in bottom-right
    toast.update_idletasks()
    x = root.winfo_x() + root.winfo_width() - toast.winfo_width() - 20
    y = root.winfo_y() + root.winfo_height() - toast.winfo_height() - 20
    toast.geometry(f"+{x}+{y}")

    # Auto-close after duration
    toast.after(duration, toast.destroy)


def serialize_vials_to_json(vials, mode, treatment_type):
    """Serialize vials into a JSON string for storage.
    
    Args:
        vials: List of Vial objects
        mode: Vial type (Environmental/Venom)
        treatment_type: Treatment type (New Start/Maintenance)
    
    Returns:
        JSON string of vial data
    """
    try:
        vial_data = []
        for vial in vials:
            vial_data.append({
                'label': vial.label,
                'allergens': vial.allergens.copy()
            })
        return json.dumps({
            'vials': vial_data,
            'vial_type': mode,
            'treatment_type': treatment_type
        })
    except Exception as e:
        print(f"Error serializing vials: {e}")
        return None


def save_patient_data(patient_data, selected_allergens, prescription_json=None):
    """Saves patient data and selected allergens to the SQLite database.

    Args:
        patient_data: Dictionary with patient information
        selected_allergens: Comma-separated string of allergen names
        prescription_json: Unused parameter kept for backward compatibility
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # Normalize all string fields to remove leading/trailing whitespace
        normalized_data = {}
        for key, value in patient_data.items():
            if isinstance(value, str):
                normalized_data[key] = value.strip()
            else:
                normalized_data[key] = value

        patient_data = normalized_data

        # Check if patient already exists by MRN (using TRIM to handle old data with trailing spaces)
        cursor.execute('SELECT id FROM patients WHERE TRIM(mrn) = ?', (patient_data['mrn'],))
        existing_patient = cursor.fetchone()

        if existing_patient:
            # Update existing patient without prompting
            cursor.execute('''
                UPDATE patients SET
                    patient_name = ?,
                    dob = ?,
                    address = ?,
                    city = ?,
                    state = ?,
                    zip_code = ?,
                    phone = ?,
                    allergens = ?,
                    treatment_type = ?,
                    prescriber_name = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE mrn = ?
            ''', (
                patient_data['patient_name'],
                patient_data['dob'].strftime("%m-%d-%Y"),
                patient_data['address'],
                patient_data['city'],
                patient_data['state'],
                patient_data.get('zip_code', ''),
                patient_data['phone'],
                selected_allergens,
                patient_data.get('treatment_type', 'New Start'),
                prescriber_var.get() if prescriber_var else "",
                patient_data['mrn']
            ))
        else:
            # Insert new patient
            cursor.execute('''
                INSERT INTO patients
                (patient_name, dob, mrn, address, city, state, zip_code, phone, allergens, treatment_type, prescriber_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                patient_data['patient_name'],
                patient_data['dob'].strftime("%m-%d-%Y"),
                patient_data['mrn'],
                patient_data['address'],
                patient_data['city'],
                patient_data['state'],
                patient_data.get('zip_code', ''),
                patient_data['phone'],
                selected_allergens,
                patient_data.get('treatment_type', 'New Start'),
                prescriber_var.get() if prescriber_var else ""
            ))

        conn.commit()
        show_toast(f"Patient '{patient_data['patient_name']}' saved successfully.")

    except sqlite3.OperationalError as e:
        error_msg = str(e).lower()
        if "database is locked" in error_msg or "disk i/o error" in error_msg:
            messagebox.showerror("Database Error",
                f"Cannot write to database (permission issue):\n{DB_FILE}\n\n"
                "Check that:\n"
                "1. The folder has write permissions\n"
                "2. The database is not on a network drive\n"
                "3. No antivirus software is blocking access\n\n"
                "Try: Settings → Change database to a local folder")
        else:
            messagebox.showerror("Database Error", f"Database error: {e}")
    except sqlite3.IntegrityError:
        messagebox.showerror("Error", f"Patient with MRN '{patient_data['mrn']}' already exists.")
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred while saving: {e}")
    finally:
        if conn:
            conn.close()


def normalize_two_digit_year(date_obj):
    """Convert 2-digit years to 4-digit years using standard cutoff (30+).

    Ages 00-29 → 2000-2029 (recent births)
    Ages 30-99 → 1930-1999 (typical patient age)

    Args:
        date_obj: datetime.date object that may have an unrealistic year

    Returns:
        datetime.date with corrected year if needed
    """
    current_year = datetime.datetime.now().year
    year = date_obj.year

    # If year is in 2000s+ but seems unrealistic (like 2086 when we typed 86)
    if year > current_year + 1:
        # This might be a 2-digit year interpretation error
        # Apply standard cutoff: 30+ → 19XX, 00-29 → 20XX
        year_2digit = year % 100
        if year_2digit >= 30:
            corrected_year = 1900 + year_2digit
        else:
            corrected_year = 2000 + year_2digit

        try:
            return date_obj.replace(year=corrected_year)
        except ValueError:
            return date_obj

    return date_obj


def load_patient():
    """Opens a new window to load an existing patient from the database."""

    def load_selected_patient():
        global last_vials, last_prescription_data, last_compounding_log_id, prescription_generated
        selected_patient_str = patient_select_var.get()
        if not selected_patient_str:
            return

        try:
            # Split the string into name and DOB parts
            name_part, dob_part = selected_patient_str.rsplit(" ", 1)
            dob_part = dob_part.strip()
            name_part = name_part.strip()

            # Convert the DOB string to a date object
            dob_to_match = datetime.datetime.strptime(dob_part, "%m-%d-%Y").date()

            # Query database - get ID so we use the same patient for prescription loading
            print(f"DEBUG: load_selected_patient - opening DB connection for patient lookup")
            conn = sqlite3.connect(DB_FILE, timeout=15)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, patient_name, dob, mrn, address, city, state, zip_code, phone, allergens, treatment_type,
                       COALESCE(prescriber_name, '') as prescriber_name
                FROM patients
                WHERE patient_name = ? AND dob = ?
            ''', (name_part, dob_part))

            result = cursor.fetchone()
            print(f"DEBUG: load_selected_patient - closing DB connection")
            conn.close()
            print(f"DEBUG: load_selected_patient - connection closed")

            if result:
                patient_id, patient_name, dob, mrn, address, city, state, zip_code, phone, allergens_str, treatment_type, prescriber_name = result
                
                # Populate the main window's fields
                patient_name_entry.delete(0, tk.END)
                patient_name_entry.insert(0, patient_name)

                # Date of Birth
                dob_date = datetime.datetime.strptime(dob, "%m-%d-%Y").date()
                dob_entry.set_date(dob_date)

                mrn_entry.delete(0, tk.END)
                mrn_entry.insert(0, mrn)
                address_entry.delete(0, tk.END)
                address_entry.insert(0, address if address else "")
                city_entry.delete(0, tk.END)
                city_entry.insert(0, city if city else "")
                state_entry.delete(0, tk.END)
                state_entry.insert(0, state if state else "")
                zip_entry.delete(0, tk.END)
                zip_entry.insert(0, zip_code if zip_code else "")
                phone_entry.delete(0, tk.END)
                phone_entry.insert(0, phone if phone else "")

                # Set prescriber name
                if prescriber_var:
                    prescriber_var.set(prescriber_name if prescriber_name else "Yashu Dhamija MD")

                # Load and set allergen checkboxes
                selected_allergens = allergens_str.split(",") if allergens_str else []

                # Clear current checkbox selections
                for var in environmental_allergen_vars.values():
                    var.set(False)
                for var in venom_allergen_vars.values():
                    var.set(False)

                # Set checkboxes based on loaded data
                if selected_allergens:
                    for allergen in selected_allergens:
                        allergen = allergen.strip()
                        if allergen in environmental_allergen_vars:
                            environmental_allergen_vars[allergen].set(True)
                        elif allergen in venom_allergen_vars:
                            venom_allergen_vars[allergen].set(True)

                # Set the Vial Type based on which allergens are selected
                if any(allergen in venom_allergen_vars for allergen in selected_allergens):
                    vial_type_var.set("Venom")
                elif any(allergen in environmental_allergen_vars for allergen in selected_allergens):
                    vial_type_var.set("Environmental")
                else:
                    vial_type_var.set("Environmental")

                # Try to load the saved prescription from database
                try:
                    # We already have patient_id from the first query, no need to look up again
                    print(f"DEBUG: Patient lookup - name='{name_part}', dob='{dob_part}' -> patient_id={patient_id}")

                    if patient_id:
                        current_vial_type = vial_type_var.get() or "Environmental"
                        print(f"DEBUG: Loading prescription for patient_id={patient_id}, vial_type={current_vial_type}")
                        vials, loaded_vial_type, loaded_treatment_type = load_prescription_from_database(patient_id, current_vial_type)
                        print(f"DEBUG: Loaded vials={len(vials) if vials else 0}, loaded_vial_type={loaded_vial_type}")

                        if vials:
                            global last_vials, last_prescription_data, last_compounding_log_id, prescription_generated
                            last_vials = vials

                            # Populate prescription data
                            last_prescription_data = {
                                'patient_name': patient_name,
                                'dob': dob,
                                'mrn': mrn,
                                'address': address,
                                'city': city,
                                'state': state,
                                'zip_code': zip_code,
                                'phone': phone,
                                'vial_type': loaded_vial_type,
                                'treatment_type': loaded_treatment_type,
                                'prescriber_name': prescriber_var.get() if prescriber_var else ""
                            }


                            # TODO: Don't create compounding log during load - create on-demand when printing
                            # This avoids database lock issues
                            # if patient_id and last_vials:
                            #     last_compounding_log_id = create_compounding_log_with_retry(...)

                            # Display the loaded prescription
                            prescription_generated = True
                            display_prescription_output(last_vials, last_prescription_data, loaded_vial_type)
                            show_toast(f"Loaded prescription for {patient_name}")
                        else:
                            # No saved prescription for this patient - clear the display
                            last_vials = []
                            last_prescription_data = {}
                            prescription_generated = False
                            result_label.config(text="", fg=TEXT_COLOR)
                            show_toast(f"No saved prescription for {patient_name}")

                except Exception as e:
                    print(f"Warning: Could not load prescription: {e}")

                # Close the dropdown before destroying the window
                patient_select_combo.event_generate('<Escape>')
                load_window.destroy()
                return

            messagebox.showwarning("Not Found", f"No patient found with Name and DOB: {selected_patient_str}")

        except Exception as e:
            messagebox.showerror("Error", f"An error occurred: {e}")

    def delete_selected_patient():
        selected_patient_str = patient_select_var.get()
        if not selected_patient_str:
            messagebox.showwarning("Warning", "Please select a patient to delete.")
            return

        # Enhanced confirmation with more details
        if not messagebox.askyesno("Confirm Delete",
            f"Are you sure you want to permanently delete this patient?\n\n{selected_patient_str}\n\nThis action cannot be undone."):
            return

        try:
            name_part, dob_part = selected_patient_str.rsplit(" ", 1)
            dob_part = dob_part.strip()
            name_part = name_part.strip()

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM patients WHERE patient_name = ? AND dob = ?",
                (name_part, dob_part)
            )
            conn.commit()
            conn.close()

            show_toast(f"Deleted patient '{selected_patient_str}'")
            # Close the dropdown before destroying the window
            patient_select_combo.event_generate('<Escape>')
            load_window.destroy()
            load_patient()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to delete patient: {e}")

    # --- Create the Load Patient Window ---
    load_window = tk.Toplevel(root)
    load_window.title("Load Patient")
    load_window.geometry("550x300")
    center_window(load_window, root)

    # Main container frame
    container = ttk.Frame(load_window, padding=15)
    container.pack(fill=tk.BOTH, expand=True)

    patient_select_label = ttk.Label(container, text="Select Patient (Name DOB):")
    patient_select_label.pack(anchor="w", pady=(0, 5))

    patient_select_var = tk.StringVar()
    patient_select_combo = ttk.Combobox(container, textvariable=patient_select_var, width=55)
    patient_select_combo.pack(pady=(0, 15))

    # Buttons - Created early so they're always visible
    button_frame = ttk.Frame(container)
    button_frame.pack(pady=(15, 0), fill=tk.X)

    load_button = ttk.Button(button_frame, text="Load", command=load_selected_patient, width=15)
    load_button.pack(side=tk.LEFT, padx=5)

    delete_button = ttk.Button(button_frame, text="Delete", command=delete_selected_patient, width=15)
    delete_button.pack(side=tk.LEFT, padx=5)

    # Store original patient data for filtering
    all_patients = []

    # Populate the dropdown with existing patient names and DOBs from database
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT patient_name, dob FROM patients ORDER BY patient_name')
        rows = cursor.fetchall()
        conn.close()

        all_patients = [{"name": row[0], "dob": row[1], "display": f"{row[0]} {row[1]}"} for row in rows]
        patient_strings = [p["display"] for p in all_patients]
        patient_select_combo['values'] = patient_strings

        if not patient_strings:
            messagebox.showinfo("No Patients", "No patient data found. Add patients first.")

    except Exception as e:
        messagebox.showerror("Error", f"Error loading patient list: {e}")


def generate_vials(selected_allergens, max_vials=3):
    """Generate vials based on selected allergens using compatibility rules.
    
    Intelligently packs allergens to fit in maximum 3 vials by:
    1. Trying to use maximum volumes
    2. Reducing volumes towards minimum if needed to fit in 3 vials
    3. Prioritizing key allergens (Cat, Timothy, Ragweed) - these are kept at max volume as long as possible
    
    Args:
        selected_allergens: List of allergen names selected by user
        
    Returns:
        List of Vial objects with allergens distributed across them
    """
    # Define priority allergens and grouping
    PRIORITY_ALLERGENS = {"Cat", "Timothy", "Ragweed"}
    POLLEN_GROUPS = {"Tree", "Grass", "Weed"}
    MAX_VIALS = max_vials
    
    allergen_map = {a["name"]: a for a in ALLERGENS}
    
    # Sort allergens strategically
    def sort_key(allergen_name):
        data = allergen_map[allergen_name]
        is_priority = allergen_name not in PRIORITY_ALLERGENS
        is_pollen = 0 if data["group"] in POLLEN_GROUPS else 1
        return (is_priority, is_pollen, -data["max_volume"])
    
    allergens_to_add = sorted(selected_allergens, key=sort_key)
    
    # Check if fit is even theoretically possible
    total_min_volume = sum(allergen_map[a]["min_volume"] for a in allergens_to_add)
    if total_min_volume > MAX_VIALS * 5.0:
        return None  # Impossible to fit
    
    # Try to pack with intelligent volume assignment
    def try_pack_vials(volume_override=None):
        """Attempt to pack allergens into vials.
        
        Args:
            volume_override: Dict mapping allergen names to specific volumes to use,
                           or None to use optimal volumes
        """
        vials = []
        
        for allergen_name in allergens_to_add:
            allergen_data = allergen_map[allergen_name]
            added = False
            
            # Determine volume to try
            if volume_override and allergen_name in volume_override:
                volumes_to_try = [volume_override[allergen_name]]
            else:
                # Priority allergens prefer max volume
                if allergen_name in PRIORITY_ALLERGENS:
                    volumes_to_try = [allergen_data["max_volume"], allergen_data["min_volume"]]
                else:
                    volumes_to_try = [allergen_data["max_volume"], allergen_data["min_volume"]]
            
            # Try to add to existing compatible vial
            vials_to_try = sorted(vials, 
                                 key=lambda v: (
                                     0 if any(allergen_map[a]["group"] == allergen_data["group"] 
                                             for a in v.allergens.keys()) else 1,
                                     -v.remaining_volume()
                                 ))
            
            for vial in vials_to_try:
                for test_volume in volumes_to_try:
                    if test_volume <= vial.remaining_volume():
                        if vial.add_allergen(allergen_name, test_volume):
                            added = True
                            break
                if added:
                    break
            
            # Create new vial if needed
            if not added:
                if len(vials) >= MAX_VIALS:
                    return None  # Can't fit in max vials with this config
                
                new_vial = Vial(f"Vial {chr(65 + len(vials))}")
                for test_volume in volumes_to_try:
                    if new_vial.add_allergen(allergen_name, test_volume):
                        added = True
                        break
                
                if not added:
                    return None
                vials.append(new_vial)
        
        return vials
    
    # First attempt: use maximum volumes where possible
    vials = try_pack_vials()
    
    # If that uses more than 3 vials, try with minimum volumes
    if vials is None or len(vials) > MAX_VIALS:
        # Create volume override with minimum values
        min_volume_override = {a: allergen_map[a]["min_volume"] 
                              for a in allergens_to_add 
                              if a not in PRIORITY_ALLERGENS}
        vials = try_pack_vials(min_volume_override)
    
    # If still doesn't fit, try even more aggressive reduction
    if vials is None or len(vials) > MAX_VIALS:
        # Use all minimum volumes
        all_min_override = {a: allergen_map[a]["min_volume"] 
                           for a in allergens_to_add}
        vials = try_pack_vials(all_min_override)
    
    if vials is None or len(vials) > MAX_VIALS:
        return None  # Cannot fit in 3 vials
    
    # Optimize vials: increase volumes where possible, prioritizing priority allergens
    for vial in vials:
        # First pass: maximize priority allergens
        for allergen_name in list(vial.allergens.keys()):
            if allergen_name in PRIORITY_ALLERGENS:
                allergen_data = allergen_map[allergen_name]
                current_volume = vial.allergens[allergen_name]
                remaining = vial.remaining_volume()
                
                if current_volume < allergen_data["max_volume"] and remaining > 0:
                    increase_amount = min(
                        allergen_data["max_volume"] - current_volume,
                        remaining
                    )
                    vial.allergens[allergen_name] += increase_amount
                    vial.current_volume += increase_amount
        
        # Second pass: maximize other allergens with remaining space
        for allergen_name in list(vial.allergens.keys()):
            if allergen_name not in PRIORITY_ALLERGENS:
                allergen_data = allergen_map[allergen_name]
                current_volume = vial.allergens[allergen_name]
                remaining = vial.remaining_volume()
                
                if current_volume < allergen_data["max_volume"] and remaining > 0:
                    increase_amount = min(
                        allergen_data["max_volume"] - current_volume,
                        remaining
                    )
                    vial.allergens[allergen_name] += increase_amount
                    vial.current_volume += increase_amount
    
    return vials


def generate_prescription():
    """Generates the prescription text with vial compositions."""
    global prescription_generated, last_prescription_data, last_vials
    mode = vial_type_var.get()
    treatment_type = treatment_type_var.get()
    prescriber_name = prescriber_var.get() if prescriber_var else ""
    patient_name = patient_name_entry.get().strip()
    mrn = mrn_entry.get().strip()
    address = address_entry.get().strip()
    city = city_entry.get().strip()
    state = state_entry.get().strip()
    zip_code = zip_entry.get().strip()
    phone = phone_entry.get().strip()

    if not patient_name or not mrn:
        messagebox.showerror("Error", "Please enter patient name and MRN.")
        return

    try:
        dob = normalize_two_digit_year(dob_entry.get_date())
    except ValueError:
        messagebox.showerror("Error", "Invalid date of birth entered.")
        return

    patient_data = {
        'patient_name': patient_name,
        'dob': dob,
        'mrn': mrn,
        'address': address,
        'city': city,
        'state': state,
        'zip_code': zip_code,
        'phone': phone,
        'treatment_type': treatment_type
    }

    # --- Collect Selected Allergens ---
    if mode == "Environmental":
        selected_allergens = [
            allergen for allergen, var in environmental_allergen_vars.items() if var.get()
        ]
    elif mode == "Venom":
        selected_allergens = [
            allergen for allergen, var in venom_allergen_vars.items() if var.get()
        ]
    else:
        result_label.config(text="Invalid vial type selected.")
        return

    # Convert to comma-separated string for saving
    selected_allergens_str = ", ".join(selected_allergens)

    if not selected_allergens:
        result_label.config(text="Error: No allergens selected.")
        return

    # Check for mutually exclusive allergens
    if "Dog - Epithelium" in selected_allergens and "Dog - UF" in selected_allergens:
        result_label.config(text="Error: Cannot select both 'Dog - Epithelium' and 'Dog - UF'.\nPlease select only one dog extract.")
        return

    # Generate vials with proper distribution (algorithm mode)
    max_vials = 4 if allow_fourth_vial_var and allow_fourth_vial_var.get() else 3
    vials = generate_vials(selected_allergens, max_vials=max_vials)

    if not vials:
        result_label.config(text="Error: Could not distribute allergens into vials.\nCheck allergen compatibility.")
        return

    # Save patient data
    save_patient_data(patient_data, selected_allergens_str)

    # Get patient ID for compounding log
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM patients WHERE mrn = ?", (mrn,))
        patient_result = cursor.fetchone()
        patient_id = patient_result[0] if patient_result else None
        conn.close()
    except:
        patient_id = None

    # Save prescription to database
    if patient_id:
        save_prescription_to_database(patient_id, vials, mode, treatment_type)

    # Store prescription data globally for PDF export
    last_prescription_data = {
        'patient_name': patient_name,
        'dob': dob.strftime('%m-%d-%Y'),
        'mrn': mrn,
        'address': address,
        'city': city,
        'state': state,
        'zip_code': zip_code,
        'phone': phone,
        'vial_type': mode,
        'treatment_type': treatment_type,
        'prescriber_name': prescriber_name
    }
    last_vials = vials

    # Create compounding log using current vial contents
    create_compounding_log(patient_id, patient_name, dob.strftime('%m-%d-%Y'), mode, treatment_type, vials, expected_mix_date_var.get())

    # Display the prescription
    display_prescription_output(last_vials, last_prescription_data, mode)

    # Mark prescription as generated
    prescription_generated = True


def display_prescription_output(vials, prescription_data, vial_type):
    """Display a prescription in the output area.
    
    Args:
        vials: List of Vial objects
        prescription_data: Dictionary with patient and prescription info
        vial_type: Type of vial (Environmental/Venom)
    """
    try:
        # Get dilution information
        dilutions = get_dilutions(vial_type, prescription_data.get('treatment_type', 'New Start'))
        
        prescription_text = f"ALLERGY IMMUNOTHERAPY PRESCRIPTION\n"
        prescription_text += f"{'='*50}\n"
        prescription_text += f"Patient Name: {prescription_data['patient_name']}\n"
        prescription_text += f"Date of Birth: {prescription_data['dob']}\n"
        prescription_text += f"MRN: {prescription_data['mrn']}\n"
        prescription_text += f"Address: {prescription_data['address']}\n"
        prescription_text += f"City: {prescription_data['city']}, {prescription_data['state']} {prescription_data.get('zip_code', '')}\n"
        prescription_text += f"Phone: {prescription_data['phone']}\n"
        prescription_text += f"Vial Type: {vial_type}\n"
        prescription_text += f"Treatment Type: {prescription_data.get('treatment_type', 'New Start')}\n"
        prescription_text += f"{'='*50}\n\n"
        
        prescription_text += f"DILUTIONS:\n"
        for color, ratio in dilutions:
            prescription_text += f"  • {color} = {ratio}\n"
        prescription_text += f"\nVIAL COMPOSITION ({len(vials)} vial(s)):\n"
        prescription_text += f"-"*50 + "\n"
        
        for vial in vials:
            prescription_text += f"\n{vial.label}:\n"
            diluent_vol = vial.remaining_volume()
            for allergen, volume in vial.allergens.items():
                if allergen == "HSA Diluent":
                    diluent_vol += volume
                    continue
                prescription_text += f"  • {allergen}: {volume:.2f} mL\n"
            prescription_text += f"  • Diluent: {diluent_vol:.2f} mL\n"
            prescription_text += f"  Total: {vial.custom_max_volume:.2f} mL\n"
        
        result_label.config(text=prescription_text)
    except Exception as e:
        result_label.config(text=f"Error displaying prescription: {e}")


def edit_prescription_volumes():
    """Open a window to manually edit allergen volumes and vial assignments in the current prescription."""
    global last_vials, last_prescription_data

    if not last_vials or not last_prescription_data:
        messagebox.showwarning("Warning", "No prescription to edit. Please generate a prescription first.")
        return

    # Create edit window
    edit_window = tk.Toplevel(root)
    edit_window.title("Edit Prescription: Volumes & Vials")
    edit_window.geometry("1125x600")
    center_window(edit_window, root)

    # Prevent duplicate windows
    if not register_window("edit_prescription_volumes", edit_window):
        return

    # Create frames for each vial
    allergen_controls = []  # List to store (allergen_name, vial_var, entry)
    
    # Canvas for scrolling
    canvas = tk.Canvas(edit_window, bg="#f0f2f5", highlightthickness=0)
    scrollbar = ttk.Scrollbar(edit_window, orient=tk.VERTICAL, command=canvas.yview)
    scrollable_frame = ttk.Frame(canvas)
    
    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # Bind mousewheel events for scrolling
    def _on_mousewheel(event):
        if event.num == 4 or event.delta > 0:
            canvas.yview_scroll(-3, "units")
        elif event.num == 5 or event.delta < 0:
            canvas.yview_scroll(3, "units")

    canvas.bind("<MouseWheel>", _on_mousewheel)
    canvas.bind("<Button-4>", _on_mousewheel)
    canvas.bind("<Button-5>", _on_mousewheel)
    scrollable_frame.bind("<MouseWheel>", _on_mousewheel)
    scrollable_frame.bind("<Button-4>", _on_mousewheel)
    scrollable_frame.bind("<Button-5>", _on_mousewheel)

    # Determine available vials for assignment
    max_allowed = 4 if (allow_fourth_vial_var and allow_fourth_vial_var.get()) else 3
    available_vials = [f"Vial {chr(65 + i)}" for i in range(max_allowed)]

    # Headers
    header_frame = ttk.Frame(scrollable_frame)
    header_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
    ttk.Label(header_frame, text="Allergen", font=("Segoe UI", 10, "bold"), width=30).pack(side=tk.LEFT)
    ttk.Label(header_frame, text="Vial Assignment", font=("Segoe UI", 10, "bold"), width=15).pack(side=tk.LEFT)
    ttk.Label(header_frame, text="Volume (mL)", font=("Segoe UI", 10, "bold"), width=15).pack(side=tk.LEFT)
    ttk.Label(header_frame, text="Quick Set", font=("Segoe UI", 10, "bold"), width=30).pack(side=tk.LEFT)

    # Helper function to create quick volume buttons for an allergen
    def create_quick_buttons(parent_frame, entry_widget, allergen_name):
        """Create quick-set volume buttons for an allergen."""
        quick_volumes = ALLERGEN_QUICK_VOLUMES.get(allergen_name, ALLERGEN_QUICK_VOLUMES.get("_default", [0.5, 1.0]))

        for volume in quick_volumes:
            def set_volume(vol=volume):
                entry_widget.delete(0, tk.END)
                entry_widget.insert(0, f"{vol:.2f}")

            btn = ttk.Button(parent_frame, text=f"{volume:.1f}", width=4, command=set_volume)
            btn.pack(side=tk.LEFT, padx=1)

    # Helper function to create vial selection buttons
    def create_vial_buttons(parent_frame, v_var, current_vial, max_vials):
        """Create compact buttons for vial selection (A, B, C, D)."""
        button_frame = ttk.Frame(parent_frame)
        button_frame.pack(side=tk.LEFT, padx=5)

        buttons = []
        vial_letters = []

        # Create all buttons first
        for i in range(max_vials):
            vial_letter = chr(65 + i)  # A, B, C, D
            full_vial_label = f"Vial {vial_letter}"

            btn = tk.Button(button_frame, text=vial_letter, width=3, relief=tk.RAISED, bd=1)
            btn.pack(side=tk.LEFT, padx=1)

            buttons.append(btn)
            vial_letters.append((vial_letter, full_vial_label))

        # Now assign commands with proper closure
        for idx, (btn, (letter, full_label)) in enumerate(zip(buttons, vial_letters)):
            def create_set_vial(vial_name, btn_idx):
                def set_vial():
                    v_var.set(vial_name)
                    # Update button styling to show selection
                    for j, b in enumerate(buttons):
                        if j == btn_idx:
                            b.config(relief=tk.SUNKEN)
                        else:
                            b.config(relief=tk.RAISED)
                return set_vial

            btn.config(command=create_set_vial(full_label, idx))

            # Highlight current selection
            if full_label == current_vial:
                btn.config(relief=tk.SUNKEN)
            else:
                btn.config(relief=tk.RAISED)


    # Build edit controls for each vial - show ALL vials (A, B, C, D), even if empty
    vial_frames = {}  # Store frame references for each vial
    vial_total_labels = {}  # Store total volume labels for updating
    vial_row_counts = {}  # Track number of rows per vial for better "Add" button placement

    # Create frames for all available vials
    for i in range(max_allowed):
        vial_label = f"Vial {chr(65 + i)}"

        # Find if this vial exists in last_vials
        existing_vial = next((v for v in last_vials if v.label == vial_label), None)
        current_total = existing_vial.current_volume if existing_vial else 0.0

        # Create vial frame with total volume
        vial_frame = ttk.LabelFrame(scrollable_frame, text=f"{vial_label} (Current Total: {current_total:.2f} mL)")
        vial_frame.pack(fill=tk.X, padx=5, pady=5)
        vial_frames[vial_label] = vial_frame

        # Store reference to label widget for updating totals dynamically
        label_text_var = tk.StringVar(value=f"{vial_label} (Current Total: {current_total:.2f} mL)")
        vial_total_labels[vial_label] = (vial_frame, label_text_var)

        vial_row_counts[vial_label] = 0

        # Add allergen rows if vial exists
        if existing_vial:
            sorted_allergen_names = sort_allergens_by_group([name for name in existing_vial.allergens.keys() if name != "HSA Diluent"])

            for allergen_name in sorted_allergen_names:
                if allergen_name == "HSA Diluent":
                    continue

                current_volume = existing_vial.allergens[allergen_name]

                row_frame = ttk.Frame(vial_frame)
                row_frame.pack(fill=tk.X, padx=5, pady=3)

                label = ttk.Label(row_frame, text=f"{allergen_name}:", width=30)
                label.pack(side=tk.LEFT, padx=5)

                v_var = tk.StringVar(value=vial_label)
                create_vial_buttons(row_frame, v_var, vial_label, max_allowed)

                entry = ttk.Entry(row_frame, width=10)
                entry.pack(side=tk.LEFT, padx=5)
                entry.insert(0, f"{current_volume:.2f}")

                # Add quick volume buttons (before mL label so they appear to the right of entry)
                create_quick_buttons(row_frame, entry, allergen_name)

                ml_label = ttk.Label(row_frame, text="mL")
                ml_label.pack(side=tk.LEFT)

                allergen_controls.append((allergen_name, v_var, entry, row_frame, False))  # False = not dynamically added
                vial_row_counts[vial_label] += 1

    # Function to add allergen row to a specific vial
    def create_add_allergen_function(target_vial_label):
        def add_allergen():
            # Get list of all allergens except HSA Diluent
            allergen_names = sorted([a["name"] for a in ALLERGENS if a["name"] != "HSA Diluent"])

            # Create a simple dialog to select allergen
            dialog = tk.Toplevel(edit_window)
            dialog.title(f"Add Allergen to {target_vial_label}")
            dialog.geometry("300x120")
            dialog.resizable(False, False)
            center_window(dialog, edit_window)

            # Allergen selection dropdown
            ttk.Label(dialog, text="Select Allergen:", font=("Segoe UI", 10)).pack(padx=10, pady=10)
            allergen_var = tk.StringVar()
            combo = ttk.Combobox(dialog, textvariable=allergen_var, values=allergen_names, state="readonly", width=30)
            combo.pack(padx=10, pady=5, fill=tk.X)

            def confirm_add():
                selected = allergen_var.get()
                if not selected:
                    messagebox.showwarning("Warning", "Please select an allergen")
                    return

                dialog.destroy()

                # Add new row to the vial
                vial_frame = vial_frames[target_vial_label]

                row_frame = ttk.Frame(vial_frame)
                row_frame.pack(fill=tk.X, padx=5, pady=3)

                allergen_label = ttk.Label(row_frame, text=f"{selected}:", width=30)
                allergen_label.pack(side=tk.LEFT, padx=5)

                v_var = tk.StringVar(value=target_vial_label)
                create_vial_buttons(row_frame, v_var, target_vial_label, max_allowed)

                entry = ttk.Entry(row_frame, width=10)
                entry.pack(side=tk.LEFT, padx=5)
                entry.insert(0, "1.00")  # Default volume

                # Add quick volume buttons (before mL label so they appear to the right of entry)
                create_quick_buttons(row_frame, entry, selected)

                ml_label = ttk.Label(row_frame, text="mL")
                ml_label.pack(side=tk.LEFT)

                # Add delete button
                def delete_row():
                    row_frame.destroy()
                    allergen_controls.remove((selected, v_var, entry, row_frame, True))

                del_button = ttk.Button(row_frame, text="✕", width=2, command=delete_row)
                del_button.pack(side=tk.LEFT, padx=2)

                allergen_controls.append((selected, v_var, entry, row_frame, True))  # True = dynamically added
                vial_row_counts[target_vial_label] += 1

            ttk.Button(dialog, text="Add", command=confirm_add).pack(side=tk.LEFT, padx=5, pady=10)
            ttk.Button(dialog, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5, pady=10)

            dialog.wait_window()

        return add_allergen

    # Add "Add Allergen" button for each vial
    for vial_label in available_vials:
        add_button_frame = ttk.Frame(vial_frames[vial_label])
        add_button_frame.pack(fill=tk.X, padx=5, pady=5)

        add_button = ttk.Button(add_button_frame, text=f"＋ Add Allergen to {vial_label}",
                               command=create_add_allergen_function(vial_label))
        add_button.pack(side=tk.LEFT)

    # Override checkbox for compatibility rules
    override_frame = ttk.Frame(edit_window)
    override_frame.pack(fill=tk.X, padx=10, pady=10)
    override_var = tk.BooleanVar(value=False)
    override_check = ttk.Checkbutton(override_frame, text="🔓 Override Compatibility Rules", variable=override_var)
    override_check.pack(side=tk.LEFT)

    # Custom vial size input
    custom_vial_frame = ttk.Frame(edit_window)
    custom_vial_frame.pack(fill=tk.X, padx=10, pady=5)

    custom_vial_var = tk.BooleanVar(value=False)
    custom_vial_check = ttk.Checkbutton(custom_vial_frame, text="Custom Vial Size (mL):", variable=custom_vial_var)
    custom_vial_check.pack(side=tk.LEFT, padx=5)

    custom_vial_size_var = tk.StringVar(value="5.0")
    custom_vial_entry = ttk.Entry(custom_vial_frame, textvariable=custom_vial_size_var, width=8, state=tk.DISABLED)
    custom_vial_entry.pack(side=tk.LEFT, padx=5)

    def toggle_custom_vial():
        """Enable/disable custom vial size entry based on checkbox."""
        if custom_vial_var.get():
            custom_vial_entry.config(state=tk.NORMAL)
            custom_vial_size_var.set(str(last_vials[0].custom_max_volume) if last_vials else "5.0")
        else:
            custom_vial_entry.config(state=tk.DISABLED)
            custom_vial_size_var.set("5.0")

    custom_vial_check.config(command=toggle_custom_vial)

    # Buttons
    button_frame = ttk.Frame(edit_window)
    button_frame.pack(fill=tk.X, padx=5, pady=10)
    
    def save_changes():
        """Validate and save vial and volume changes."""
        global last_vials, last_prescription_data
        try:
            # Get custom vial size if enabled
            max_vial_volume = 5.0
            if custom_vial_var.get():
                try:
                    max_vial_volume = float(custom_vial_size_var.get())
                    if max_vial_volume <= 0:
                        messagebox.showerror("Error", "Custom vial size must be greater than 0 mL")
                        return
                    if max_vial_volume > 100.0:  # Reasonable upper limit
                        messagebox.showerror("Error", "Custom vial size exceeds reasonable limit (100 mL)")
                        return
                except ValueError:
                    messagebox.showerror("Error", "Invalid custom vial size. Please enter a number.")
                    return

            new_vial_assignments = {} # label -> {name: vol}

            # Collect and validate all entries - handle new 5-tuple structure
            for control_tuple in allergen_controls:
                allergen_name, v_var, entry, row_frame, is_dynamic = control_tuple
                vial_label = v_var.get()
                try:
                    new_vol = float(entry.get())
                    if new_vol < 0.01:
                        messagebox.showerror("Error", f"{allergen_name}: minimum volume is 0.01 mL")
                        return
                    if new_vol > max_vial_volume:
                        messagebox.showerror("Error", f"{allergen_name}: maximum volume is {max_vial_volume} mL for this vial size")
                        return
                except ValueError:
                    messagebox.showerror("Error", f"Invalid volume for {allergen_name}")
                    return

                if vial_label not in new_vial_assignments:
                    new_vial_assignments[vial_label] = {}

                # Handle allergen splitting: if same allergen in same vial multiple times, sum them
                if allergen_name in new_vial_assignments[vial_label]:
                    new_vial_assignments[vial_label][allergen_name] += new_vol
                else:
                    new_vial_assignments[vial_label][allergen_name] = new_vol

            # Check total volumes per vial and auto-adjust if needed
            for label, allergens in new_vial_assignments.items():
                total = sum(allergens.values())

                # If total exceeds custom max volume, proportionally scale down allergens to fit
                if total > max_vial_volume:
                    scale_factor = (max_vial_volume - 0.1) / total  # Leave 0.1 mL for diluent
                    for allergen_name in allergens:
                        allergens[allergen_name] = round(allergens[allergen_name] * scale_factor, 2)
                    messagebox.showinfo("Auto-Adjusted",
                        f"{label}: Allergen volumes exceeded {max_vial_volume} mL. "
                        f"Volumes have been proportionally scaled to fit in the vial.")

            # Create new Vial objects and enforce compatibility
            updated_vials = []
            allergen_map = {a["name"]: a for a in ALLERGENS}

            for label in sorted(new_vial_assignments.keys()):
                vial = Vial(label)
                vial.custom_max_volume = max_vial_volume  # Set custom vial size
                for name, vol in new_vial_assignments[label].items():
                    # Skip adding diluent here, we'll add it after compatibility checks
                    if name == "HSA Diluent":
                        continue

                    allergen_data = allergen_map.get(name)
                    if allergen_data:
                        # Check compatibility (unless override is enabled)
                        if not override_var.get() and not vial.is_compatible(allergen_data):
                            # Find which allergen it conflict with for a better error message
                            conflict_name = "existing contents"
                            for existing_name in vial.allergens.keys():
                                temp_vial = Vial("Temp")
                                temp_vial.allergens[existing_name] = 1.0 # dummy
                                if not temp_vial.is_compatible(allergen_data):
                                    conflict_name = existing_name
                                    break

                            messagebox.showerror("Compatibility Error",
                                f"Incompatible Move: Cannot put '{name}' in {label}.\n\n"
                                f"It is incompatible with {conflict_name} according to clinical rules.")
                            return

                    vial.allergens[name] = vol
                    vial.current_volume += vol

                # Automatically calculate and add HSA Diluent to reach custom max volume
                diluent_needed = max_vial_volume - vial.current_volume
                if diluent_needed > 0:
                    vial.allergens["HSA Diluent"] = round(diluent_needed, 2)
                    vial.current_volume = max_vial_volume

                updated_vials.append(vial)

            last_vials = updated_vials

            # Update prescription display
            display_prescription_output(last_vials, last_prescription_data, last_prescription_data['vial_type'])

            # Get patient MRN and save updated prescription to database
            mrn = last_prescription_data.get('mrn')
            if mrn:
                try:
                    conn = sqlite3.connect(DB_FILE)
                    cursor = conn.cursor()
                    cursor.execute("SELECT id FROM patients WHERE mrn = ?", (mrn,))
                    row = cursor.fetchone()
                    if row:
                        patient_id = row[0]
                        # Save updated prescription to database
                        save_prescription_to_database(
                            patient_id,
                            last_vials,
                            last_prescription_data['vial_type'],
                            last_prescription_data['treatment_type']
                        )
                        # Update/re-create compounding log
                        create_compounding_log(
                            patient_id,
                            last_prescription_data['patient_name'],
                            last_prescription_data['dob'],
                            last_prescription_data['vial_type'],
                            last_prescription_data['treatment_type'],
                            last_vials,
                            expected_mix_date_var.get()
                        )
                    conn.close()
                except Exception as e:
                    print(f"Warning: Could not save prescription: {e}")

            show_toast("Prescription updated")
            edit_window.destroy()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to save changes: {e}")
    
    save_button = ttk.Button(button_frame, text="Save Changes", command=save_changes)
    save_button.pack(side=tk.LEFT, padx=5)
    
    cancel_button = ttk.Button(button_frame, text="Cancel", command=edit_window.destroy)
    cancel_button.pack(side=tk.LEFT, padx=5)


def get_dilutions(vial_type, treatment_type):
    """Returns list of (color, ratio) tuples for dilutions based on vial and treatment type."""
    if vial_type == "Environmental":
        if treatment_type == "New Start":
            return [("Red", "1:1"), ("Yellow", "1:10"), ("Blue", "1:100"), ("Green", "1:1,000"), ("Silver", "1:10,000")]
        else:  # Maintenance
            return [("Red", "1:1")]
    else:  # Venom
        return [("Red", "1:1"), ("Yellow", "1:10"), ("Blue", "1:100")]


def get_allergen_abbreviation(allergen_name):
    """Get abbreviation for Other group allergens, or return full name for other groups."""
    abbreviation_map = {
        "Cat": "C",
        "Dog - UF": "D",
        "Dog - Epithelium": "D",
        "Mouse": "M",
        "Rat": "R",
        "Horse": "H",
        "Amer. Cockroach": "CR",
        "Ger. Cockroach": "CR",
        "Dust Mite Mix": "DM"
    }
    return abbreviation_map.get(allergen_name, allergen_name)


def export_prescription_to_pdf():
    """Exports the current prescription to a PDF file with signature lines."""
    global last_save_directory
    if not last_prescription_data or not last_vials:
        messagebox.showwarning("Warning", "Please generate a prescription first before exporting.")
        return

    # Determine prescription type prefix (AIT for Environmental, VIT for Venom)
    vial_type = last_prescription_data.get('vial_type', 'Environmental')
    prefix = "VIT" if vial_type == "Venom" else "AIT"

    # Ask user where to save the file
    file_path = filedialog.asksaveasfilename(
        initialdir=last_save_directory,
        defaultextension=".pdf",
        filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")],
        initialfile=f"{last_prescription_data['patient_name'].replace(' ', '_')}_{prefix}_Prescription.pdf"
    )
    
    if not file_path:
        return
    
    # Remember the directory for next time
    last_save_directory = os.path.dirname(file_path)
    CURRENT_CONFIG['last_save_directory'] = last_save_directory
    save_config(CURRENT_CONFIG)
    
    try:
        # Create PDF document with compact margins
        doc = SimpleDocTemplate(file_path, pagesize=letter, topMargin=0.4*inch, bottomMargin=0.4*inch, 
                                leftMargin=0.5*inch, rightMargin=0.5*inch)
        styles = getSampleStyleSheet()
        story = []
        
        # Compact custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=12,
            textColor=colors.HexColor('#1f77d2'),
            spaceAfter=3,
            alignment=1  # Center alignment
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=9,
            textColor=colors.HexColor('#0d5bba'),
            spaceAfter=2
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=8,
            spaceAfter=1
        )
        
        # Title
        title = Paragraph("ALLERGY IMMUNOTHERAPY PRESCRIPTION", title_style)
        story.append(title)
        story.append(Spacer(1, 0.08*inch))
        
        # Patient Information Table - Compact
        patient_info = [
            ['Patient:', last_prescription_data['patient_name'], 'DOB:', last_prescription_data['dob']],
            ['MRN:', last_prescription_data['mrn'], 'Phone:', last_prescription_data['phone']],
            ['Address:', last_prescription_data['address'], 'Zip:', last_prescription_data.get('zip_code', '')],
            ['City, State:', f"{last_prescription_data['city']}, {last_prescription_data['state']}", 'Type:', last_prescription_data['vial_type']]
        ]
        
        patient_table = Table(patient_info, colWidths=[0.8*inch, 1.8*inch, 0.6*inch, 1.8*inch])
        patient_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f2f5')),
            ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#f0f2f5')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2)
        ]))
        story.append(patient_table)
        story.append(Spacer(1, 0.08*inch))
        
        # Dilutions Section - Compact
        dilutions = get_dilutions(last_prescription_data['vial_type'], last_prescription_data['treatment_type'])
        dilution_heading = Paragraph("<b>Dilutions</b>", heading_style)
        story.append(dilution_heading)

        for color, ratio in dilutions:
            dilution_para = Paragraph(f"{color} = {ratio}", normal_style)
            story.append(dilution_para)
        story.append(Spacer(1, 0.06*inch))

        # Vial Composition Section - Compact with treatment type label
        treatment_label = last_prescription_data.get('treatment_type', 'New Start')
        if treatment_label == "New Start":
            treatment_label = "Build Up"
        composition_heading = Paragraph(f"<b>{treatment_label} - VIAL COMPOSITION ({len(last_vials)} vial(s))</b>", heading_style)
        story.append(composition_heading)
        story.append(Spacer(1, 0.04*inch))
        
        for vial in last_vials:
            # Vial header
            vial_header = Paragraph(f"<b>{vial.label}</b>", heading_style)
            story.append(vial_header)
            
            # Vial contents table
            vial_contents = []
            diluent_vol = vial.remaining_volume()

            # Sort allergens by group priority
            sorted_allergen_names = sort_allergens_by_group([name for name in vial.allergens.keys() if name != "HSA Diluent"])

            for allergen_name in sorted_allergen_names:
                volume = vial.allergens[allergen_name]
                vial_contents.append([allergen_name, f"{volume:.2f} mL"])

            # Check if HSA Diluent exists in vial and use its volume
            if "HSA Diluent" in vial.allergens:
                diluent_vol = vial.allergens["HSA Diluent"]

            vial_contents.append(["Diluent:", f"{diluent_vol:.2f} mL"])
            
            vial_table = Table(vial_contents, colWidths=[3.5*inch, 0.8*inch])

            # Build table style with alternating row colors
            table_style = [
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                ('TOPPADDING', (0, 0), (-1, -1), 1),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 1)
            ]

            # Add alternating row colors
            for row_idx in range(len(vial_contents)):
                if row_idx % 2 == 0:
                    table_style.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor('#f5f5f5')))
                else:
                    table_style.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.white))

            # Highlight diluent row with light blue
            table_style.append(('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8f4f8')))

            vial_table.setStyle(TableStyle(table_style))
            story.append(vial_table)
            story.append(Spacer(1, 0.04*inch))
        
        story.append(Spacer(1, 0.08*inch))
        
        # Signature section - Compact
        sig_heading = Paragraph("<b>Prescriber Information</b>", heading_style)
        story.append(sig_heading)
        
        # Get current date for auto-population
        current_date = datetime.datetime.now().strftime("%m-%d-%Y")
        
        # Signature table - wider and with more vertical space
        prescriber_name = last_prescription_data.get('prescriber_name', '')
        sig_data = [
            ['Signature: _________________________________', f'Date: {current_date}'],
            ['', ''],  # Empty row for spacing
            [f'Printed Name: {prescriber_name}', 'Phone: 513-458-1800']
        ]
        
        sig_table = Table(sig_data, colWidths=[3.75*inch, 2.0*inch])
        sig_table.setStyle(TableStyle([
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTSIZE', (0, 0), (-1, 2), 8),
            ('GRID', (0, 0), (-1, -1), 0, colors.white),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 2), (-1, 2), 8),
            ('BOTTOMPADDING', (0, 2), (-1, 2), 8),
            ('TOPPADDING', (0, 1), (-1, 1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, 1), 6)
        ]))
        story.append(sig_table)
        
        # Build PDF
        doc.build(story)
        show_toast("Prescription exported successfully", duration=5000,
                  link_text="Open Folder",
                  link_action=lambda fp=file_path: os.startfile(os.path.dirname(fp)))
    
    except Exception as e:
        messagebox.showerror("Error", f"Failed to export PDF: {e}")


def calculate_lot_number(dob_date):
    """Calculate lot number from current date + patient DOB as digits only.
    
    Format: MMDDYYYYMMDDYYYY (current date + DOB, no separators)
    Example: 02052026 (today) + 05151990 (DOB) = 0205202605151990
    """
    current_date = datetime.datetime.now()
    current_str = current_date.strftime('%m%d%Y')
    
    # Handle both datetime.date and string formats
    if isinstance(dob_date, str):
        # Parse MM-DD-YYYY format
        dob_parts = dob_date.split('-')
        dob_str = f"{dob_parts[0]}{dob_parts[1]}{dob_parts[2]}"
    else:
        # datetime.date object
        dob_str = dob_date.strftime('%m%d%Y')
    
    return current_str + dob_str


def calculate_vial_expiration(mix_date_str, items_list):
    """Calculate vial expiration date: whichever comes first -
    1 year from mix date OR earliest stock extract expiration.
    
    Args:
        mix_date_str: Mix date as string in '%m-%d-%Y' format
        items_list: List of items with 'expiration_date' field
    
    Returns:
        Expiration date as string in '%m/%d/%Y' format
    """
    def get_expiration_field(item):
        if item is None:
            return None
        if isinstance(item, dict):
            return item.get('expiration_date')
        try:
            return item['expiration_date']
        except Exception:
            return getattr(item, 'expiration_date', None)

    try:
        mix_date_obj = datetime.datetime.strptime(mix_date_str, '%m-%d-%Y')
        one_year_expiration = mix_date_obj.replace(year=mix_date_obj.year + 1)

        # Find earliest expiration date among all stock extracts
        earliest_stock_expiration = None
        for item in items_list:
            expiration_field = get_expiration_field(item)
            if expiration_field:
                stock_exp_date = parse_expiration_date(expiration_field)
                if stock_exp_date and (earliest_stock_expiration is None or stock_exp_date < earliest_stock_expiration):
                    earliest_stock_expiration = stock_exp_date

        # Vial expires on whichever is earlier
        if earliest_stock_expiration and earliest_stock_expiration < one_year_expiration.date():
            vial_expiration_obj = earliest_stock_expiration
        else:
            vial_expiration_obj = one_year_expiration.date()

        return vial_expiration_obj.strftime('%m/%d/%Y')
    except Exception:
        return "TBD"


def parse_expiration_date(date_str):
    """Parse expiration dates in common formats. Returns date or None."""
    if not date_str:
        return None
    cleaned = str(date_str).strip()
    if not cleaned:
        return None
    for fmt in ("%m-%d-%Y", "%m/%d/%Y", "%m-%d-%y", "%m/%d/%y"):
        try:
            return datetime.datetime.strptime(cleaned, fmt).date()
        except Exception:
            continue
    return None


def generate_label_data(mix_date=None):
    """Generate label data for all vials with their dilutions.

    Args:
        mix_date: Optional mix date string in format "mm/dd/yyyy". If not provided, uses today's date.

    Returns a list of dictionaries with label information.
    For each vial, creates one label per dilution based on treatment type.
    """
    if not last_prescription_data or not last_vials:
        return []

    labels = []
    vial_type = last_prescription_data['vial_type']
    treatment_type = last_prescription_data['treatment_type']
    patient_name = last_prescription_data['patient_name']
    dob = last_prescription_data['dob']

    # Get dilutions for this prescription
    dilutions = get_dilutions(vial_type, treatment_type)

    # Get mix date - use provided date or default to today
    if mix_date:
        # Convert mm/dd/yyyy to mm-dd-yyyy for consistency
        current_date = mix_date.replace("/", "-")
    else:
        current_date = datetime.datetime.now().strftime('%m-%d-%Y')
    lot_number = calculate_lot_number(dob)
    
    # Get vial expiration dates from database for each vial
    vial_expirations = {}
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if last_compounding_log_id:
            cursor.execute('''
                SELECT vial_letter, expiration_date 
                FROM compounding_log_items 
                WHERE compounding_log_id = ?
            ''', (last_compounding_log_id,))
            items = cursor.fetchall()
            
            # Group by vial and calculate expiration for each
            items_by_vial = {}
            for item in items:
                vial = item['vial_letter']
                if vial not in items_by_vial:
                    items_by_vial[vial] = []
                items_by_vial[vial].append(dict(item))
            
            # Calculate expiration for each vial
            for vial_letter, vial_items in items_by_vial.items():
                vial_expirations[vial_letter] = calculate_vial_expiration(current_date, vial_items)
        
        conn.close()
    except Exception as e:
        print(f"Warning: Could not retrieve vial expiration dates: {e}")
    
    # Get unique allergen groups in each vial
    for vial in last_vials:
        allergen_groups = set()
        other_group_abbrevs = []

        for allergen_name in vial.allergens.keys():
            allergen_data = next((a for a in ALLERGENS if a["name"] == allergen_name), None)
            if allergen_data:
                group = allergen_data["group"]
                if group == "Other":
                    # For Other group, use abbreviations
                    other_group_abbrevs.append(get_allergen_abbreviation(allergen_name))
                else:
                    allergen_groups.add(group)

        # Sort allergen groups by priority and add Other group abbreviations at the end
        sorted_groups = sorted(allergen_groups, key=lambda g: GROUP_ORDER.index(g) if g in GROUP_ORDER else len(GROUP_ORDER))

        # Add abbreviated Other group allergens
        if other_group_abbrevs:
            sorted_groups.append(", ".join(sorted(other_group_abbrevs)))

        allergen_groups_str = ", ".join(sorted_groups)
        
        # Get expiration for this vial
        vial_expiration = vial_expirations.get(vial.label, "TBD")
        
        # Create one label per dilution
        for dilution_color, dilution_ratio in dilutions:
            label_data = {
                'label_type': 'vial',
                'patient_name': patient_name,
                'dob': dob,
                'vial_letter': vial.label,
                'dilution_color': dilution_color,
                'dilution_ratio': dilution_ratio,
                'allergen_groups': allergen_groups_str,
                'mix_date': current_date,
                'lot_number': lot_number,
                'expiration': vial_expiration,
            }
            labels.append(label_data)

        # Add one bag label per vial (no dilution info)
        bag_label_data = {
            'label_type': 'bag',
            'patient_name': patient_name,
            'dob': dob,
            'vial_letter': vial.label,
            'expiration': vial_expiration,
            'mix_date': current_date,
            'lot_number': lot_number,
        }
        labels.append(bag_label_data)

    # Add two patient-set labels per prescription (type only)
    # Use the earliest vial expiration for the patient-set label
    earliest_expiration = "TBD"
    if vial_expirations:
        try:
            expiration_dates = [parse_expiration_date(exp) for exp in vial_expirations.values() if exp != "TBD"]
            if expiration_dates:
                earliest_expiration = min(expiration_dates).strftime('%m/%d/%Y')
        except:
            pass
    
    for _ in range(2):
        patient_set_label = {
            'label_type': 'patient_set',
            'patient_name': patient_name,
            'dob': dob,
            'vial_type': vial_type,
            'expiration': earliest_expiration,
        }
        labels.append(patient_set_label)
    
    return labels


def generate_labels_pdf(file_path, mix_date=None):
    """Generate a PDF with labels in Avery 45160 format.

    Creates a multi-page PDF if needed, with all labels properly positioned
    on Avery 45160 label sheets.

    Args:
        file_path: Path to save the PDF
        mix_date: Optional mix date string in format "mm/dd/yyyy"
    """
    try:
        label_data_list = generate_label_data(mix_date)

        if not label_data_list:
            messagebox.showerror("Error", "No prescription generated. Please generate a prescription first.")
            return

        # Create PDF
        c = canvas.Canvas(file_path, pagesize=(8.5*inch, 11*inch))
        
        spec = LABEL_AVERY_SPECS
        label_width = spec['label_width'] * inch
        label_height = spec['label_height'] * inch
        top_margin = spec['top_margin'] * inch
        left_margin = spec['left_margin'] * inch
        col_gap = spec['col_gap'] * inch
        current_row = 0
        current_col = 0
        
        for label_info in label_data_list:
            # Check if we need a new page
            if current_row >= spec['rows']:
                c.showPage()
                current_row = 0
                current_col = 0
            
            # Calculate position
            x = left_margin + (current_col * (label_width + col_gap))
            y = (11 * inch) - top_margin - (label_height * (current_row + 1))
            
            # Draw label rectangle (border)
            c.setLineWidth(0.5)
            c.rect(x, y, label_width, label_height)
            
            # Set font for label
            c.setFont("Helvetica-Bold", 10)
            text_offset = 15 / 72 * inch
            text_y = y + label_height - 0.08 * inch - text_offset + (10 / 72 * inch)
            
            # Patient name (line 1)
            c.drawString(x + 0.05*inch, text_y, label_info['patient_name'])
            text_y -= 0.12*inch
            
            # DOB (line 2, smaller text)
            c.setFont("Helvetica", 7)
            c.drawString(x + 0.05*inch, text_y, f"DOB: {label_info['dob']}")
            dob_gap = 3 / 72 * inch
            text_y -= 0.09*inch + dob_gap

            if label_info.get('label_type') == 'bag':
                # Bag label: vial letter only
                c.setFont("Helvetica-Bold", 10)
                c.drawString(x + 0.05*inch, text_y, f"Vial {label_info['vial_letter']}")
                text_y -= 0.12*inch
                c.setFont("Helvetica", 7)
                c.drawString(x + 0.05*inch, text_y, f"Exp: {label_info['expiration']}")
                text_y -= 0.08*inch
                c.setFont("Helvetica", 6.5)
                c.drawString(x + 0.05*inch, text_y, f"Mix: {label_info['mix_date']}")
                text_y -= 0.08*inch
                c.setFont("Helvetica", 6)
                c.drawString(x + 0.05*inch, text_y, f"Lot: {label_info['lot_number']}")
                text_y -= 0.08*inch
                c.setFont("Helvetica", 6)
                c.drawString(x + 0.05*inch, text_y, "Storage: Refrigeration at 2°C – 8°C (36°F – 46°F)")
            elif label_info.get('label_type') == 'patient_set':
                # Patient set label: vial type and expiration
                c.setFont("Helvetica-Bold", 10)
                c.drawString(x + 0.05*inch, text_y, label_info['vial_type'])
                text_y -= 0.12*inch
                c.setFont("Helvetica", 7)
                c.drawString(x + 0.05*inch, text_y, f"Exp: {label_info['expiration']}")
                text_y -= 0.08*inch
                c.setFont("Helvetica", 6)
                c.drawString(x + 0.05*inch, text_y, "Storage: Refrigeration at 2°C – 8°C (36°F – 46°F)")
            else:
                # Vial Letter + Dilution (line 3, prominent)
                c.setFont("Helvetica-Bold", 9)
                c.drawString(x + 0.05*inch, text_y, f"Vial {label_info['vial_letter']} - {label_info['dilution_color']}")
                c.setFont("Helvetica", 7)
                c.drawString(x + 0.5*inch, text_y - 0.08*inch, f"({label_info['dilution_ratio']})")
                text_y -= 0.15*inch
                
                # Allergen groups (line 4)
                c.setFont("Helvetica", 6.5)
                c.drawString(x + 0.05*inch, text_y, f"Groups: {label_info['allergen_groups']}")
                text_y -= 0.09*inch
                
                # Mix Date and Expiration (line 5)
                c.setFont("Helvetica", 6.5)
                c.drawString(x + 0.05*inch, text_y, f"Mix: {label_info['mix_date']}")
                c.drawString(x + 1.3*inch, text_y, f"Exp: {label_info['expiration']}")
                text_y -= 0.08*inch
                
                # Lot Number (line 6)
                c.setFont("Helvetica", 6)
                c.drawString(x + 0.05*inch, text_y, f"Lot: {label_info['lot_number']}")
                text_y -= 0.08*inch
                
                # Storage instructions (line 7)
                c.setFont("Helvetica", 6)
                c.drawString(x + 0.05*inch, text_y, "Storage: Refrigeration at 2°C – 8°C (36°F – 46°F)")
            
            # Move to next position
            current_col += 1
            if current_col >= spec['cols']:
                current_col = 0
                current_row += 1
        
        # Save the final page
        c.save()
        show_toast("Labels exported successfully", duration=5000,
                  link_text="Open Folder",
                  link_action=lambda fp=file_path: os.startfile(os.path.dirname(fp)))
        
    except Exception as e:
        messagebox.showerror("Error", f"Failed to generate labels: {e}")


def export_labels():
    """Export labels to a PDF file using Avery 45160 format."""
    global last_save_directory
    if not last_prescription_data or not last_vials:
        messagebox.showerror("Error", "No prescription generated. Please generate a prescription first.")
        return

    # Create default filename
    patient_name = last_prescription_data['patient_name'].replace(" ", "_")
    current_date = datetime.datetime.now().strftime("%m%d%Y")
    default_filename = f"Labels_{patient_name}_{current_date}.pdf"

    file_path = filedialog.asksaveasfilename(
        initialdir=last_save_directory,
        defaultextension=".pdf",
        filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        initialfile=default_filename
    )

    if file_path:
        last_save_directory = os.path.dirname(file_path)
        CURRENT_CONFIG['last_save_directory'] = last_save_directory
        save_config(CURRENT_CONFIG)
        # Pass expected mix date if one was set
        mix_date = expected_mix_date_var.get() if expected_mix_date_var else None
        generate_labels_pdf(file_path, mix_date)


def save_prescription_to_database(patient_id, vials, vial_type, treatment_type):
    """Save the current prescription (vials and volumes) to the database.

    Args:
        patient_id: ID of the patient
        vials: List of Vial objects
        vial_type: Type of vial (Environmental/Venom)
        treatment_type: Treatment type (New Start/Maintenance)
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=10)
        cursor = conn.cursor()

        # Get the max_volume from the first vial (all should be the same)
        max_volume = vials[0].custom_max_volume if vials else 5.0

        # Check if max_volume column exists (for backwards compatibility)
        cursor.execute("PRAGMA table_info(patient_prescriptions)")
        columns = [col[1] for col in cursor.fetchall()]
        has_max_volume = 'max_volume' in columns

        # Check if prescription exists for this patient AND vial type
        cursor.execute("SELECT id FROM patient_prescriptions WHERE patient_id = ? AND vial_type = ?", (patient_id, vial_type))
        existing = cursor.fetchone()

        if existing:
            prescription_id = existing[0]
            # Update existing prescription
            if has_max_volume:
                cursor.execute('''
                    UPDATE patient_prescriptions
                    SET treatment_type = ?, max_volume = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (treatment_type, max_volume, prescription_id))
            else:
                # Backwards compatibility: don't update max_volume if column doesn't exist
                cursor.execute('''
                    UPDATE patient_prescriptions
                    SET treatment_type = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (treatment_type, prescription_id))
            # Clear old vial entries
            cursor.execute("DELETE FROM patient_prescription_vials WHERE prescription_id = ?", (prescription_id,))
        else:
            # Create new prescription record
            if has_max_volume:
                cursor.execute('''
                    INSERT INTO patient_prescriptions (patient_id, vial_type, treatment_type, max_volume)
                    VALUES (?, ?, ?, ?)
                ''', (patient_id, vial_type, treatment_type, max_volume))
            else:
                # Backwards compatibility: don't include max_volume if column doesn't exist
                cursor.execute('''
                    INSERT INTO patient_prescriptions (patient_id, vial_type, treatment_type)
                    VALUES (?, ?, ?)
                ''', (patient_id, vial_type, treatment_type))
            prescription_id = cursor.lastrowid

        # Save all vials and their allergens
        for vial in vials:
            for allergen_name, volume in vial.allergens.items():
                cursor.execute('''
                    INSERT INTO patient_prescription_vials
                    (prescription_id, vial_letter, allergen_name, volume)
                    VALUES (?, ?, ?, ?)
                ''', (prescription_id, vial.label, allergen_name, volume))

        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Warning: Could not save prescription to database: {e}")
    finally:
        if conn:
            conn.close()


def load_prescription_from_database(patient_id, vial_type):
    """Load the saved prescription from the database for a patient and vial type.

    Args:
        patient_id: ID of the patient
        vial_type: Type of vial to load (Environmental/Venom)

    Returns tuple of (vials, vial_type, treatment_type) or (None, None, None) if not found
    """
    conn = None
    try:
        print(f"DEBUG: load_prescription - opening DB connection (timeout 15s)")
        conn = sqlite3.connect(DB_FILE, timeout=15)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        print(f"DEBUG: load_prescription - opened DB_FILE={DB_FILE}")

        # Check if max_volume column exists (for backwards compatibility)
        cursor.execute("PRAGMA table_info(patient_prescriptions)")
        columns = [col[1] for col in cursor.fetchall()]
        has_max_volume = 'max_volume' in columns
        print(f"DEBUG: load_prescription - max_volume column exists: {has_max_volume}")

        # Get the patient prescription for the specific vial type
        # Handle backwards compatibility: old records may have vial_type=NULL (treat as Environmental default)
        if has_max_volume:
            sql_query = '''
                SELECT id, vial_type, treatment_type, COALESCE(max_volume, 5.0) as max_volume
                FROM patient_prescriptions
                WHERE patient_id = ? AND (vial_type = ? OR (vial_type IS NULL AND ? = 'Environmental'))
                LIMIT 1
            '''
        else:
            # Backwards compatibility: old schema without max_volume column
            sql_query = '''
                SELECT id, vial_type, treatment_type, 5.0 as max_volume
                FROM patient_prescriptions
                WHERE patient_id = ? AND (vial_type = ? OR (vial_type IS NULL AND ? = 'Environmental'))
                LIMIT 1
            '''

        print(f"DEBUG: load_prescription - executing query with patient_id={patient_id}, vial_type={vial_type}")
        print(f"DEBUG: load_prescription - SQL query:\n{sql_query}")
        print(f"DEBUG: load_prescription - query params: ({patient_id}, {vial_type}, {vial_type})")
        cursor.execute(sql_query, (patient_id, vial_type, vial_type))

        prescription = cursor.fetchone()
        print(f"DEBUG: load_prescription - query returned: {prescription}")

        # Also check if there are ANY prescriptions for this patient at all
        cursor.execute("SELECT id, patient_id, vial_type FROM patient_prescriptions WHERE patient_id = ?", (patient_id,))
        all_prescriptions = cursor.fetchall()
        print(f"DEBUG: load_prescription - ALL prescriptions for patient_id={patient_id}: {len(all_prescriptions)} records")
        for pres in all_prescriptions:
            print(f"  Prescription: id={pres[0]}, patient_id={pres[1]}, vial_type={pres[2]}")

        if not prescription:
            print(f"DEBUG: No prescription found for patient_id={patient_id}, vial_type={vial_type}")
            print(f"DEBUG: load_prescription - closing connection (no prescription found)")
            conn.close()
            return None, None, None

        prescription_id = prescription['id']
        vial_type = prescription['vial_type'] or "Environmental"  # Handle NULL vial_type from old records
        treatment_type = prescription['treatment_type']
        max_volume = prescription['max_volume']
        print(f"DEBUG: Found prescription_id={prescription_id}, vial_type={vial_type}, treatment_type={treatment_type}")

        # Get all vial data
        cursor.execute('''
            SELECT vial_letter, allergen_name, volume
            FROM patient_prescription_vials
            WHERE prescription_id = ?
            ORDER BY vial_letter, allergen_name
        ''', (prescription_id,))
        items = cursor.fetchall()
        print(f"DEBUG: Found {len(items)} vial items for prescription_id={prescription_id}")

        # Reconstruct vials (include all allergens and diluent)
        vials_dict = {}
        diluent_dict = {}
        for item in items:
            allergen_name = item['allergen_name']
            vial_letter = item['vial_letter']
            volume = item['volume']

            if allergen_name == "HSA Diluent":
                # Store diluent separately to add after calculating remaining volume
                if vial_letter not in diluent_dict:
                    diluent_dict[vial_letter] = volume
            else:
                if vial_letter not in vials_dict:
                    vials_dict[vial_letter] = {}
                vials_dict[vial_letter][allergen_name] = volume

        # Create Vial objects with custom max volume
        vials = []
        for vial_letter in sorted(vials_dict.keys()):
            vial = Vial(vial_letter)
            vial.custom_max_volume = max_volume  # Set the custom max volume for this vial
            for allergen_name, volume in vials_dict[vial_letter].items():
                vial.allergens[allergen_name] = volume
                vial.current_volume += volume

            # Add the diluent if it exists for this vial
            if vial_letter in diluent_dict:
                vial.allergens["HSA Diluent"] = diluent_dict[vial_letter]
                vial.current_volume += diluent_dict[vial_letter]
            else:
                # Calculate diluent as remaining volume to custom max volume
                remaining = max_volume - vial.current_volume
                if remaining > 0:
                    vial.allergens["HSA Diluent"] = remaining
                    vial.current_volume = max_volume

            vials.append(vial)

        print(f"DEBUG: load_prescription - successfully loaded {len(vials)} vials, closing connection")
        return vials, vial_type, treatment_type
    except Exception as e:
        print(f"Warning: Could not load prescription from database: {e}")
        return None, None, None
    finally:
        if conn:
            print(f"DEBUG: load_prescription - finally block: closing connection")
            conn.close()
            print(f"DEBUG: load_prescription - connection closed in finally")


def get_stock_for_allergen(allergen_name, require_active=False):
    """Return the preferred stock record for an allergen (active first)."""
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if require_active:
            cursor.execute('''
                SELECT * FROM stock_extracts
                WHERE allergen_name = ? AND is_active = 1
                ORDER BY expiration_date ASC, created_at DESC
                LIMIT 1
            ''', (allergen_name,))
        else:
            cursor.execute('''
                SELECT * FROM stock_extracts
                WHERE allergen_name = ?
                ORDER BY is_active DESC, expiration_date ASC, created_at DESC
                LIMIT 1
            ''', (allergen_name,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        messagebox.showerror("Error", f"Failed to load stock for {allergen_name}: {e}")
        return None


def create_compounding_log_with_retry(patient_id, patient_name, dob, vial_type, treatment_type, vials, mix_date=None):
    """Wrapper that retries create_compounding_log if database is locked."""
    import time
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return create_compounding_log(patient_id, patient_name, dob, vial_type, treatment_type, vials, mix_date)
        except Exception as e:
            if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                print(f"DEBUG: Database locked, retrying in 0.5s (attempt {attempt + 1}/{max_retries})")
                time.sleep(0.5)
            else:
                print(f"DEBUG: Could not create compounding log: {e}")
                return None
    return None


def create_compounding_log(patient_id, patient_name, dob, vial_type, treatment_type, vials, mix_date=None):
    """Create a compounding log record for the generated prescription.

    Args:
        mix_date: Optional mix date string in format "mm/dd/yyyy". If not provided, uses today's date.

    Returns the compounding log ID.
    """
    global last_compounding_log_id
    conn = None

    try:
        # Use provided mix date or default to today
        if mix_date:
            # Convert mm/dd/yyyy to mm-dd-yyyy for consistency
            current_date = mix_date.replace("/", "-")
        else:
            current_date = datetime.datetime.now().strftime("%m-%d-%Y")

        lot_number = calculate_lot_number(dob)

        print(f"DEBUG: create_compounding_log - opening DB connection")
        conn = sqlite3.connect(DB_FILE, timeout=15)
        cursor = conn.cursor()

        # Check if log already exists for this lot
        cursor.execute("SELECT id FROM compounding_logs WHERE lot_number = ?", (lot_number,))
        existing = cursor.fetchone()
        if existing:
            compounding_log_id = existing[0]
            cursor.execute('''
                UPDATE compounding_logs
                SET patient_id = ?, patient_name = ?, dob = ?, vial_type = ?, treatment_type = ?, mix_date = ?
                WHERE id = ?
            ''', (patient_id, patient_name, dob, vial_type, treatment_type, current_date, compounding_log_id))
            cursor.execute("DELETE FROM compounding_log_items WHERE compounding_log_id = ?", (compounding_log_id,))
        else:
            # Create new compounding log
            cursor.execute('''
                INSERT INTO compounding_logs
                (patient_id, patient_name, dob, vial_type, treatment_type, mix_date, lot_number)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (patient_id, patient_name, dob, vial_type, treatment_type, current_date, lot_number))
            compounding_log_id = cursor.lastrowid

        # Add items for each vial and allergen (including HSA Diluent)
        for vial in vials:
            # Sort allergens by group priority (include diluent)
            sorted_allergen_names = sort_allergens_by_group([name for name in vial.allergens.keys()])
            for allergen_name in sorted_allergen_names:
                volume_used = vial.allergens[allergen_name]
                stock = get_stock_for_allergen(allergen_name, require_active=True)
                if not stock:
                    stock = get_stock_for_allergen(allergen_name)
                cursor.execute('''
                    INSERT INTO compounding_log_items
                    (compounding_log_id, vial_letter, allergen_name, volume_used, stock_extract_id,
                     concentration, manufacturer_item, lot_number, expiration_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    compounding_log_id,
                    vial.label,
                    allergen_name,
                    volume_used,
                    stock['id'] if stock else None,
                    stock.get('concentration', '') if stock else '',
                    stock.get('manufacturer_item', '') if stock else '',
                    stock.get('lot_number', '') if stock else '',
                    stock.get('expiration_date', '') if stock else ''
                ))

        # Add dilution vials based on treatment type
        dilution_vials_to_add = [("Red Top - empty 5 mL", "Red Top - Empty")]  # (full_name, short_name)
        if treatment_type == "New Start":  # Build-up option
            dilution_vials_to_add.extend([
                ("Normal Saline with Human Serum Albumin - Yellow Top", "Yellow Top w/ HSA"),
                ("Normal Saline with Human Serum Albumin - Blue Top", "Blue Top w/ HSA"),
                ("Normal Saline with Human Serum Albumin - Green Top", "Green Top w/ HSA"),
                ("Normal Saline with Human Serum Albumin - Silver Top", "Silver Top w/ HSA")
            ])

        # Calculate quantity of dilution vials needed (one per vial being compounded)
        num_vials = len(vials)

        # Insert dilution vial items into compounding log
        for full_name, short_name in dilution_vials_to_add:
            stock = get_stock_for_allergen(full_name, require_active=True)
            if not stock:
                # Try to find in stock_extracts table even if not tagged as allergen
                try:
                    conn2 = sqlite3.connect(DB_FILE)
                    conn2.row_factory = sqlite3.Row
                    cursor2 = conn2.cursor()
                    cursor2.execute("SELECT * FROM stock_extracts WHERE allergen_name = ? ORDER BY is_active DESC, created_at DESC LIMIT 1", (full_name,))
                    stock_row = cursor2.fetchone()
                    stock = dict(stock_row) if stock_row else None
                    conn2.close()
                except:
                    stock = None

            if stock:
                cursor.execute('''
                    INSERT INTO compounding_log_items
                    (compounding_log_id, vial_letter, allergen_name, volume_used, stock_extract_id,
                     concentration, manufacturer_item, lot_number, expiration_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    compounding_log_id,
                    "Empty Vials Used",
                    short_name,
                    float(num_vials),
                    stock.get('id') if isinstance(stock, dict) else stock['id'],
                    stock.get('concentration', '') if isinstance(stock, dict) else stock.get('concentration', ''),
                    stock.get('manufacturer_item', '') if isinstance(stock, dict) else stock.get('manufacturer_item', ''),
                    stock.get('lot_number', '') if isinstance(stock, dict) else stock.get('lot_number', ''),
                    stock.get('expiration_date', '') if isinstance(stock, dict) else stock.get('expiration_date', '')
                ))

        conn.commit()
        print(f"DEBUG: create_compounding_log - closing DB connection")

        last_compounding_log_id = compounding_log_id
        return compounding_log_id

    except Exception as e:
        print(f"Error: Failed to create compounding log: {e}")
        messagebox.showerror("Error", f"Failed to create compounding log: {e}")
        return None
    finally:
        if conn:
            print(f"DEBUG: create_compounding_log - finally block: closing connection")
            conn.close()
            print(f"DEBUG: create_compounding_log - connection closed")


def export_compounding_log_pdf():
    """Export the compounding log to a PDF file."""
    global last_compounding_log_id

    # If no compounding log exists but we have a loaded prescription, create one on-demand
    if not last_compounding_log_id and last_prescription_data and last_vials:
        print("DEBUG: export_compounding_log_pdf - creating compounding log on-demand")
        last_compounding_log_id = create_compounding_log_with_retry(
            last_prescription_data.get('patient_id', ''),
            last_prescription_data.get('patient_name', ''),
            last_prescription_data.get('dob', ''),
            last_prescription_data.get('vial_type', 'Environmental'),
            last_prescription_data.get('treatment_type', 'New Start'),
            last_vials,
            expected_mix_date_var.get() if expected_mix_date_var else None
        )

    if not last_compounding_log_id:
        messagebox.showerror("Error", "No compounding log generated. Please generate a prescription first.")
        return
    
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get compounding log
        cursor.execute("SELECT * FROM compounding_logs WHERE id = ?", (last_compounding_log_id,))
        log = cursor.fetchone()
        
        if not log:
            conn.close()
            messagebox.showerror("Error", "Compounding log not found.")
            return
        
        # Get all items for this log
        cursor.execute('''
            SELECT * FROM compounding_log_items 
            WHERE compounding_log_id = ?
            ORDER BY vial_letter, allergen_name
        ''', (last_compounding_log_id,))
        items = cursor.fetchall()
        
        conn.close()
        
        # Ask for save location
        global last_save_directory
        patient_name = log['patient_name'].replace(" ", "_")
        default_filename = f"CompoundingLog_{patient_name}_{log['lot_number']}.pdf"
        
        file_path = filedialog.asksaveasfilename(
            initialdir=last_save_directory,
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
            initialfile=default_filename
        )
        
        if not file_path:
            return
        
        # Remember the directory for next time
        last_save_directory = os.path.dirname(file_path)
        CURRENT_CONFIG['last_save_directory'] = last_save_directory
        save_config(CURRENT_CONFIG)
        
        # Generate PDF
        try:
            doc = SimpleDocTemplate(file_path, pagesize=letter, topMargin=0.4*inch, bottomMargin=0.4*inch,
                                    leftMargin=0.5*inch, rightMargin=0.5*inch)
            styles = getSampleStyleSheet()
            story = []
            
            # Title
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=14,
                textColor=colors.HexColor('#1f77d2'),
                spaceAfter=3,
                alignment=1
            )
            
            heading_style = ParagraphStyle(
                'CustomHeading',
                parent=styles['Heading2'],
                fontSize=10,
                textColor=colors.HexColor('#0d5bba'),
                spaceAfter=2
            )
            
            normal_style = ParagraphStyle(
                'CustomNormal',
                parent=styles['Normal'],
                fontSize=8,
                spaceAfter=1
            )
            
            title = Paragraph("COMPOUNDING LOG", title_style)
            story.append(title)
            story.append(Spacer(1, 0.1*inch))
            
            # Patient info
            patient_info = [
                ['Patient Name:', log['patient_name'], 'DOB:', log['dob']],
                ['Vial Type:', log['vial_type'], 'Treatment Type:', log['treatment_type']],
                ['Mix Date:', log['mix_date'], 'Lot Number:', log['lot_number']]
            ]
            
            patient_table = Table(patient_info, colWidths=[1.2*inch, 1.8*inch, 1.2*inch, 1.8*inch])
            patient_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f2f5')),
                ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#f0f2f5')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2)
            ]))
            story.append(patient_table)
            story.append(Spacer(1, 0.08*inch))
            
            # Get dilutions
            dilutions = get_dilutions(log['vial_type'], log['treatment_type'])
            dilution_heading = Paragraph("<b>Dilutions Prepared:</b>", heading_style)
            story.append(dilution_heading)
            dilution_text = ", ".join([f"{color} ({ratio})" for color, ratio in dilutions])
            story.append(Paragraph(dilution_text, normal_style))
            story.append(Spacer(1, 0.08*inch))
            
            # Compounding details
            compound_heading = Paragraph("<b>Compounding Details:</b>", heading_style)
            story.append(compound_heading)
            
            # Group items by vial
            items_by_vial = {}
            for item in items:
                vial_letter = item['vial_letter']
                if vial_letter not in items_by_vial:
                    items_by_vial[vial_letter] = []
                items_by_vial[vial_letter].append(item)
            
            # Create table for each vial
            for vial_letter in sorted(items_by_vial.keys()):
                vial_items = items_by_vial[vial_letter]

                # Use appropriate heading based on vial letter
                if vial_letter == "Empty Vials Used":
                    vial_heading = Paragraph(f"<b>{vial_letter}</b>", heading_style)
                else:
                    # Get stock data for this vial to ensure we have actual expiration dates
                    vial_expiration_str = "TBD"
                    try:
                        stock_items = []
                        for item in vial_items:
                            if item['stock_extract_id']:
                                # Look up stock extract to get actual expiration date
                                conn_exp = sqlite3.connect(DB_FILE)
                                conn_exp.row_factory = sqlite3.Row
                                cursor_exp = conn_exp.cursor()
                                cursor_exp.execute(
                                    "SELECT expiration_date FROM stock_extracts WHERE id = ?",
                                    (item['stock_extract_id'],)
                                )
                                stock_row = cursor_exp.fetchone()
                                conn_exp.close()
                                if stock_row and stock_row['expiration_date']:
                                    stock_items.append({'expiration_date': stock_row['expiration_date']})

                        # If we found stock items with expiration dates, calculate properly
                        if stock_items:
                            vial_expiration_str = calculate_vial_expiration(log['mix_date'], stock_items)
                        else:
                            # Fallback: try to calculate from items already loaded
                            vial_expiration_str = calculate_vial_expiration(log['mix_date'], vial_items)
                    except Exception as e:
                        print(f"Warning: Could not retrieve stock expiration for vial {vial_letter}: {e}")
                        vial_expiration_str = calculate_vial_expiration(log['mix_date'], vial_items)

                    vial_heading = Paragraph(f"<b>{vial_letter}</b> (Mixed: {log['mix_date']} | Expires: {vial_expiration_str})", heading_style)
                story.append(vial_heading)

                # Add Qty column for dilution vials, omit for allergens
                if vial_letter == "Empty Vials Used":
                    vial_data = [['Item', 'Qty', 'Concentration', 'Manuf. Item #', 'Lot #', 'Expiration']]
                else:
                    vial_data = [['Allergen', 'Volume', 'Concentration', 'Manuf. Item #', 'Lot #', 'Expiration']]

                for item in vial_items:
                    if vial_letter == "Empty Vials Used":
                        # For dilution vials, show quantity instead of volume with mL
                        vial_data.append([
                            item['allergen_name'],
                            f"{int(item['volume_used'])}",
                            item['concentration'] or '-',
                            item['manufacturer_item'] or '-',
                            item['lot_number'] or '-',
                            item['expiration_date'] or '-'
                        ])
                    else:
                        # For allergens, show volume with mL
                        vial_data.append([
                            item['allergen_name'],
                            f"{item['volume_used']:.2f} mL",
                            item['concentration'] or '-',
                            item['manufacturer_item'] or '-',
                            item['lot_number'] or '-',
                            item['expiration_date'] or '-'
                        ])

                vial_table = Table(vial_data, colWidths=[1.0*inch, 0.8*inch, 1.0*inch, 1.0*inch, 0.8*inch, 0.8*inch])
                vial_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0d5bba')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('ALIGN', (1, 0), (1, -1), 'CENTER'),
                    ('FONTSIZE', (0, 0), (-1, -1), 7),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('LEFTPADDING', (0, 0), (-1, -1), 2),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                    ('TOPPADDING', (0, 0), (-1, -1), 1),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 1)
                ]))
                story.append(vial_table)
                story.append(Spacer(1, 0.04*inch))
            
            story.append(Spacer(1, 0.1*inch))

            # Quality control and signatures
            qc_heading = Paragraph("<b>Quality Control & Verification</b>", heading_style)
            story.append(qc_heading)

            # Get vial size from last_vials if available
            vial_size = last_vials[0].custom_max_volume if last_vials else 5.0
            qc_text = f"Final Yield per vial: {vial_size:.1f} mL<br/>Quality Control Procedures: Color top confirmed; no particulates."
            story.append(Paragraph(qc_text, normal_style))
            story.append(Spacer(1, 0.08*inch))
            
            # Signature lines
            prepared_by_name = mix_preparer_var.get() if mix_preparer_var else ""
            sig_data = [
                [f'Prepared by: {prepared_by_name}', 'Date: _______________'],
                ['', ''],
                ['Verified by: _____________________________', 'Vial ID (Lot #): ' + log['lot_number']]
            ]
            
            sig_table = Table(sig_data, colWidths=[3.25*inch, 2.75*inch])
            sig_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0, colors.white),
                ('TOPPADDING', (0, 0), (-1, 0), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('TOPPADDING', (0, 2), (-1, 2), 8),
                ('BOTTOMPADDING', (0, 2), (-1, 2), 8)
            ]))
            story.append(sig_table)
            
            # Build PDF
            doc.build(story)
            show_toast("Compounding log exported successfully", duration=5000,
                      link_text="Open Folder",
                      link_action=lambda fp=file_path: os.startfile(os.path.dirname(fp)))
        
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate compounding log PDF: {e}")
    
    except Exception as e:
        messagebox.showerror("Error", f"Failed to export compounding log: {e}")


def enforce_dog_mutual_exclusivity(*args):
    """Ensures only one dog extract (Epithelium or UF) can be selected at a time."""
    dog_epithelium_selected = environmental_allergen_vars.get("Dog - Epithelium", tk.BooleanVar()).get()
    dog_uf_selected = environmental_allergen_vars.get("Dog - UF", tk.BooleanVar()).get()
    
    # If both are selected, uncheck Dog - UF (keeping the one that was checked first)
    if dog_epithelium_selected and dog_uf_selected:
        environmental_allergen_vars["Dog - UF"].set(False)


def show_stock_edit_dialog(stock_id=None, parent_window=None):
    """Show dialog to add or edit a stock extract entry.
    
    If stock_id is None, this is an add operation. Otherwise, it's an edit.
    parent_window: reference to parent window to refresh after save.
    """
    try:
        edit_window = tk.Toplevel(root)
        edit_window.title("Add Stock Entry" if stock_id is None else "Edit Stock Entry")
        edit_window.geometry("500x450")
        center_window(edit_window, root)

        # Get allergen names for dropdown
        allergen_names = get_stock_allergen_names()
        
        # If editing, fetch current data
        current_data = {}
        if stock_id:
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM stock_extracts WHERE id = ?", (stock_id,))
            result = cursor.fetchone()
            conn.close()
            if result:
                current_data = dict(result)
        
        # Create form fields
        form_frame = ttk.Frame(edit_window, padding=20)
        form_frame.pack(fill=tk.BOTH, expand=True)
        
        # Allergen Name
        ttk.Label(form_frame, text="Allergen Name:", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=10)
        allergen_var = tk.StringVar(value=current_data.get('allergen_name', ''))
        allergen_combo = ttk.Combobox(form_frame, textvariable=allergen_var, values=allergen_names, state='readonly', width=40)
        allergen_combo.grid(row=0, column=1, sticky="ew", pady=10)
        
        # Concentration
        ttk.Label(form_frame, text="Concentration:", font=("Segoe UI", 10, "bold")).grid(row=1, column=0, sticky="w", pady=10)
        concentration_var = tk.StringVar(value=current_data.get('concentration', ''))
        concentration_entry = ttk.Entry(form_frame, textvariable=concentration_var, width=40)
        concentration_entry.grid(row=1, column=1, sticky="ew", pady=10)
        
        # Manufacturer Item
        ttk.Label(form_frame, text="Manuf. Item #:", font=("Segoe UI", 10, "bold")).grid(row=2, column=0, sticky="w", pady=10)
        manuf_var = tk.StringVar(value=current_data.get('manufacturer_item', ''))
        manuf_entry = ttk.Entry(form_frame, textvariable=manuf_var, width=40)
        manuf_entry.grid(row=2, column=1, sticky="ew", pady=10)
        
        # Lot Number
        ttk.Label(form_frame, text="Lot Number:", font=("Segoe UI", 10, "bold")).grid(row=3, column=0, sticky="w", pady=10)
        lot_var = tk.StringVar(value=current_data.get('lot_number', ''))
        lot_entry = ttk.Entry(form_frame, textvariable=lot_var, width=40)
        lot_entry.grid(row=3, column=1, sticky="ew", pady=10)
        
        # Expiration Date
        ttk.Label(form_frame, text="Expiration (MM-DD-YYYY):", font=("Segoe UI", 10, "bold")).grid(row=4, column=0, sticky="w", pady=10)
        exp_var = tk.StringVar(value=current_data.get('expiration_date', ''))
        exp_entry = ttk.Entry(form_frame, textvariable=exp_var, width=40)
        exp_entry.grid(row=4, column=1, sticky="ew", pady=10)
        
        # Vial Amount
        ttk.Label(form_frame, text="Vial Amount (mL):", font=("Segoe UI", 10, "bold")).grid(row=5, column=0, sticky="w", pady=10)
        vial_var = tk.StringVar(value=current_data.get('vial_amount', ''))
        vial_entry = ttk.Entry(form_frame, textvariable=vial_var, width=40)
        vial_entry.grid(row=5, column=1, sticky="ew", pady=10)
        
        form_frame.columnconfigure(1, weight=1)
        
        # Button frame
        button_frame = ttk.Frame(edit_window)
        button_frame.pack(fill=tk.X, padx=20, pady=20)
        
        def save_entry():
            allergen = allergen_var.get().strip()
            concentration = concentration_var.get().strip()
            manuf = manuf_var.get().strip()
            lot = lot_var.get().strip()
            expiration = exp_var.get().strip()
            vial_amt = vial_var.get().strip()
            
            if not allergen or not lot:
                messagebox.showwarning("Validation", "Allergen Name and Lot Number are required.")
                return
            
            try:
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                
                if stock_id:
                    # Update existing
                    cursor.execute('''
                        UPDATE stock_extracts
                        SET allergen_name = ?, concentration = ?, manufacturer_item = ?,
                            lot_number = ?, expiration_date = ?, vial_amount = ?
                        WHERE id = ?
                    ''', (allergen, concentration, manuf, lot, expiration, vial_amt, stock_id))
                    action_text = "updated"
                else:
                    # Insert new
                    cursor.execute('''
                        INSERT INTO stock_extracts
                        (allergen_name, concentration, manufacturer_item, lot_number, expiration_date, vial_amount, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, 0)
                    ''', (allergen, concentration, manuf, lot, expiration, vial_amt))
                    action_text = "added"
                
                conn.commit()
                conn.close()
                
                show_toast(f"Stock entry {action_text}")
                edit_window.destroy()
                
                # Refresh parent window if provided
                if parent_window:
                    parent_window.destroy()
                    show_inventory_and_staff()
            
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save entry: {e}")
        
        save_btn = ttk.Button(button_frame, text="💾 Save", command=save_entry)
        save_btn.pack(side=tk.LEFT, padx=5)
        
        cancel_btn = ttk.Button(button_frame, text="Cancel", command=edit_window.destroy)
        cancel_btn.pack(side=tk.LEFT, padx=5)

    except Exception as e:
        messagebox.showerror("Error", f"Failed to open edit dialog: {e}")


def get_staff_members():
    """Get list of staff members from database."""
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM staff_members ORDER BY name")
        rows = cursor.fetchall()
        conn.close()
        return [row['name'] for row in rows]
    except Exception as e:
        messagebox.showerror("Error", f"Failed to load staff members: {e}")
        return []


def refresh_staff_dropdowns():
    """Update prescriber and preparer dropdowns with current staff members."""
    global prescriber_combo, mix_preparer_combo
    staff = get_staff_members()
    if prescriber_combo:
        prescriber_combo['values'] = staff
    if mix_preparer_combo:
        mix_preparer_combo['values'] = staff


def show_staff_edit_dialog(staff_id=None, parent_window=None):
    """Show dialog to add or edit a staff member."""
    try:
        edit_window = tk.Toplevel(root)
        edit_window.title("Add Staff Member" if staff_id is None else "Edit Staff Member")
        edit_window.geometry("400x200")
        center_window(edit_window, root)

        # Get current data if editing
        current_data = {}
        if staff_id:
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM staff_members WHERE id = ?", (staff_id,))
            result = cursor.fetchone()
            conn.close()
            if result:
                current_data = dict(result)

        # Create form fields
        form_frame = ttk.Frame(edit_window, padding=20)
        form_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(form_frame, text="Staff Name:", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=10)
        name_var = tk.StringVar(value=current_data.get('name', ''))
        name_entry = ttk.Entry(form_frame, textvariable=name_var, width=40)
        name_entry.grid(row=0, column=1, sticky="ew", pady=10)

        ttk.Label(form_frame, text="Role:", font=("Segoe UI", 10, "bold")).grid(row=1, column=0, sticky="w", pady=10)
        role_var = tk.StringVar(value=current_data.get('role', ''))
        role_combo = ttk.Combobox(form_frame, textvariable=role_var,
                                  values=["Prescriber", "Preparer", "Both"], state='readonly', width=38)
        role_combo.grid(row=1, column=1, sticky="ew", pady=10)

        form_frame.columnconfigure(1, weight=1)

        # Button frame
        button_frame = ttk.Frame(edit_window)
        button_frame.pack(fill=tk.X, padx=20, pady=20)

        def save_entry():
            name = name_var.get().strip()
            role = role_var.get().strip()

            if not name:
                messagebox.showwarning("Validation", "Staff name is required.")
                return

            try:
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()

                if staff_id:
                    cursor.execute('''
                        UPDATE staff_members
                        SET name = ?, role = ?
                        WHERE id = ?
                    ''', (name, role, staff_id))
                    action_text = "updated"
                else:
                    cursor.execute('''
                        INSERT INTO staff_members (name, role)
                        VALUES (?, ?)
                    ''', (name, role))
                    action_text = "added"

                conn.commit()
                conn.close()

                show_toast(f"Staff member {action_text}")
                refresh_staff_dropdowns()
                edit_window.destroy()

                if parent_window:
                    parent_window.destroy()
                    show_inventory_and_staff()

            except sqlite3.IntegrityError:
                messagebox.showerror("Error", f"Staff member '{name}' already exists.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save entry: {e}")

        save_btn = ttk.Button(button_frame, text="💾 Save", command=save_entry)
        save_btn.pack(side=tk.LEFT, padx=5)

        cancel_btn = ttk.Button(button_frame, text="Cancel", command=edit_window.destroy)
        cancel_btn.pack(side=tk.LEFT, padx=5)

    except Exception as e:
        messagebox.showerror("Error", f"Failed to open edit dialog: {e}")



def show_inventory_and_staff():
    """Open Inventory & Staff window with tabbed interface."""
    try:
        main_window = tk.Toplevel(root)
        main_window.title("Inventory & Staff Management")
        main_window.geometry("1200x650")
        center_window(main_window, root)

        # Prevent duplicate windows
        if not register_window("inventory_and_staff", main_window):
            return

        # Create notebook (tabbed interface)
        notebook = ttk.Notebook(main_window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # ===== TAB 1: INVENTORY =====
        inventory_tab = ttk.Frame(notebook)
        notebook.add(inventory_tab, text="📦 Inventory")

        def fetch_stocks(filter_allergen=None, filter_group=None):
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get all stocks first
            cursor.execute('''
                SELECT id, allergen_name, concentration, manufacturer_item, lot_number,
                       expiration_date, vial_amount, is_active
                FROM stock_extracts
                ORDER BY allergen_name, is_active DESC, expiration_date ASC
            ''')
            all_stocks = cursor.fetchall()
            conn.close()

            # Filter by group (using ALLERGENS data)
            if filter_group and filter_group != "All":
                allergen_map = {a["name"]: a["group"] for a in ALLERGENS}
                all_stocks = [s for s in all_stocks if allergen_map.get(s['allergen_name']) == filter_group]

            # Filter by allergen name
            if filter_allergen and filter_allergen != "All":
                all_stocks = [s for s in all_stocks if s['allergen_name'] == filter_allergen]

            return all_stocks

        def fetch_allergen_options():
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute('SELECT DISTINCT allergen_name FROM stock_extracts ORDER BY allergen_name')
            names = [row[0] for row in cursor.fetchall()]
            conn.close()
            return ["All"] + names

        def fetch_group_options():
            """Get unique groups from ALLERGENS that have stock items."""
            allergen_map = {a["name"]: a["group"] for a in ALLERGENS}
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute('SELECT DISTINCT allergen_name FROM stock_extracts')
            allergen_names = [row[0] for row in cursor.fetchall()]
            conn.close()

            groups = set()
            for allergen_name in allergen_names:
                group = allergen_map.get(allergen_name)
                if group:
                    groups.add(group)

            return ["All"] + sorted(groups)

        # Filter controls
        filter_frame = ttk.Frame(inventory_tab)
        filter_frame.pack(fill=tk.X, padx=10, pady=(10, 0))

        ttk.Label(filter_frame, text="Filter by Type:").pack(side=tk.LEFT, padx=(0, 5))
        type_filter_var = tk.StringVar(value="All")
        type_filter_combo = ttk.Combobox(filter_frame, textvariable=type_filter_var,
                             values=fetch_group_options(), state='readonly', width=15)
        type_filter_combo.pack(side=tk.LEFT, padx=(0, 15))

        ttk.Label(filter_frame, text="Filter by Allergen:").pack(side=tk.LEFT)
        allergen_filter_var = tk.StringVar(value="All")
        allergen_filter_combo = ttk.Combobox(filter_frame, textvariable=allergen_filter_var,
                             values=fetch_allergen_options(), state='readonly', width=30)
        allergen_filter_combo.pack(side=tk.LEFT, padx=6)

        # Create treeview
        frame = ttk.Frame(inventory_tab)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        columns = ("ID", "Allergen", "Concentration", "Manuf. Item", "Lot", "Expiration", "Vial Amt", "Active")
        tree = ttk.Treeview(frame, columns=columns, height=20, selectmode='extended')

        tree.column("#0", width=0, stretch=tk.NO)
        col_widths = {"ID": 30, "Allergen": 120, "Concentration": 100, "Manuf. Item": 100,
                     "Lot": 100, "Expiration": 100, "Vial Amt": 80, "Active": 50}

        def parse_sort_value(col, value):
            if col == "ID":
                try:
                    return int(value)
                except Exception:
                    return 0
            if col == "Expiration":
                try:
                    return datetime.datetime.strptime(value, "%m-%d-%Y")
                except Exception:
                    return datetime.datetime.max
            if col == "Vial Amt":
                try:
                    cleaned = str(value).lower().replace("ml", "").strip()
                    return float(cleaned)
                except Exception:
                    return float("inf")
            if col == "Active":
                return 0 if str(value).strip() == "✓" else 1
            return str(value).lower()

        sort_state = {}

        def sort_by_column(col):
            rows = []
            for row_id in tree.get_children():
                values = tree.item(row_id)["values"]
                rows.append({c: values[i] for i, c in enumerate(columns)})

            reverse = sort_state.get(col, False)
            sort_state[col] = not reverse
            rows.sort(key=lambda r: parse_sort_value(col, r[col]), reverse=reverse)

            for row_id in tree.get_children():
                tree.delete(row_id)

            current_tag = 'allergen_light'
            last_allergen = None
            for row in rows:
                allergen_name = row["Allergen"]
                if last_allergen is None:
                    last_allergen = allergen_name
                elif allergen_name != last_allergen:
                    current_tag = 'allergen_dark' if current_tag == 'allergen_light' else 'allergen_light'
                    last_allergen = allergen_name

                row_tags = [current_tag]
                if is_expiring_soon(row["Expiration"]):
                    row_tags.append('expiring_soon')
                tree.insert("", "end", values=(
                    row["ID"],
                    row["Allergen"],
                    row["Concentration"],
                    row["Manuf. Item"],
                    row["Lot"],
                    row["Expiration"],
                    row["Vial Amt"],
                    row["Active"],
                ), tags=tuple(row_tags))

        for col in columns:
            tree.column(col, width=col_widths.get(col, 100))
            tree.heading(col, text=col, command=lambda c=col: sort_by_column(c))

        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tree.configure(yscroll=scrollbar.set)

        # Bind mousewheel events for scrolling
        def _on_tree_mousewheel(event):
            if event.num == 4 or event.delta > 0:
                tree.yview_scroll(-3, "units")
            elif event.num == 5 or event.delta < 0:
                tree.yview_scroll(3, "units")

        tree.bind("<MouseWheel>", _on_tree_mousewheel)
        tree.bind("<Button-4>", _on_tree_mousewheel)
        tree.bind("<Button-5>", _on_tree_mousewheel)

        tree.tag_configure('allergen_light', background='#ffffff')
        tree.tag_configure('allergen_dark', background='#f0f2f5')
        tree.tag_configure('expiring_soon', background='#fff3b0')

        def is_expiring_soon(expiration_str):
            exp_date = parse_expiration_date(expiration_str if expiration_str != '-' else '')
            if not exp_date:
                return False
            today = datetime.datetime.now().date()
            cutoff = today + datetime.timedelta(days=365)
            return exp_date <= cutoff

        def populate_tree(filter_allergen=None, filter_group=None):
            for row_id in tree.get_children():
                tree.delete(row_id)
            current_tag = 'allergen_light'
            last_allergen = None
            for stock in fetch_stocks(filter_allergen, filter_group):
                if last_allergen is None:
                    last_allergen = stock['allergen_name']
                elif stock['allergen_name'] != last_allergen:
                    current_tag = 'allergen_dark' if current_tag == 'allergen_light' else 'allergen_light'
                    last_allergen = stock['allergen_name']
                active_str = "✓" if stock['is_active'] else " "
                row_tags = [current_tag]
                if is_expiring_soon(stock['expiration_date'] or '-'):
                    row_tags.append('expiring_soon')
                tree.insert("", "end", values=(
                    stock['id'],
                    stock['allergen_name'],
                    stock['concentration'] or '-',
                    stock['manufacturer_item'] or '-',
                    stock['lot_number'],
                    stock['expiration_date'] or '-',
                    stock['vial_amount'] or '-',
                    active_str
                ), tags=tuple(row_tags))

        def refresh_expiring_highlights():
            for row_id in tree.get_children():
                values = tree.item(row_id).get("values", [])
                expiration = values[5] if len(values) > 5 else "-"
                tags = list(tree.item(row_id).get("tags", ()))
                tags = [t for t in tags if t != 'expiring_soon']
                if is_expiring_soon(expiration):
                    tags.append('expiring_soon')
                tree.item(row_id, tags=tuple(tags))
            main_window.after(5000, refresh_expiring_highlights)

        def apply_filter(*args):
            populate_tree(allergen_filter_var.get(), type_filter_var.get())

        type_filter_combo.bind("<<ComboboxSelected>>", apply_filter)
        allergen_filter_combo.bind("<<ComboboxSelected>>", apply_filter)
        populate_tree()
        refresh_expiring_highlights()

        # Add buttons for inventory tab
        button_frame = ttk.Frame(inventory_tab)
        button_frame.pack(fill=tk.X, padx=10, pady=10)

        def add_entry():
            show_stock_edit_dialog(stock_id=None, parent_window=main_window)

        def edit_entry(selected_item=None):
            if selected_item is None:
                selected = tree.selection()
                if not selected:
                    messagebox.showwarning("Warning", "Please select a stock item to edit.")
                    return
                selected_item = selected[0]

            values = tree.item(selected_item)['values']
            stock_id = values[0]
            show_stock_edit_dialog(stock_id=stock_id, parent_window=main_window)

        def on_tree_double_click(event):
            selected_item = tree.focus()
            if selected_item:
                edit_entry(selected_item)

        tree.bind("<Double-1>", on_tree_double_click)

        def delete_entry():
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("Warning", "Please select one or more stock items to delete.")
                return

            entries = []
            for selected_item in selected:
                values = tree.item(selected_item)['values']
                entries.append((values[0], values[1], values[4]))

            if messagebox.askyesno("Confirm Delete",
                f"Are you sure you want to permanently delete {len(entries)} selected item(s)?\n\nThis action cannot be undone."):
                try:
                    conn = sqlite3.connect(DB_FILE)
                    cursor = conn.cursor()
                    cursor.executemany("DELETE FROM stock_extracts WHERE id = ?", [(entry[0],) for entry in entries])
                    conn.commit()
                    conn.close()

                    show_toast(f"Deleted {len(entries)} item(s)")
                    main_window.destroy()
                    show_inventory_and_staff()

                except Exception as e:
                    messagebox.showerror("Error", f"Failed to delete entry: {e}")

        def set_active():
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("Warning", "Please select one or more stock items.")
                return

            entries = []
            for selected_item in selected:
                values = tree.item(selected_item)['values']
                entries.append((values[0], values[1], values[4]))

            try:
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()

                allergen_names = sorted({entry[1] for entry in entries})
                for allergen_name in allergen_names:
                    cursor.execute(
                        "UPDATE stock_extracts SET is_active = 0 WHERE allergen_name = ?",
                        (allergen_name,)
                    )

                cursor.executemany(
                    "UPDATE stock_extracts SET is_active = 1 WHERE id = ?",
                    [(entry[0],) for entry in entries]
                )

                conn.commit()
                conn.close()

                show_toast(f"Set {len(entries)} item(s) as active")
                main_window.destroy()
                show_inventory_and_staff()

            except Exception as e:
                messagebox.showerror("Error", f"Failed to update stock: {e}")

        add_btn = ttk.Button(button_frame, text="➕ Add Entry", command=add_entry)
        add_btn.pack(side=tk.LEFT, padx=5)

        edit_btn = ttk.Button(button_frame, text="✏️ Edit", command=edit_entry)
        edit_btn.pack(side=tk.LEFT, padx=5)

        delete_btn = ttk.Button(button_frame, text="🗑️ Delete", command=delete_entry)
        delete_btn.pack(side=tk.LEFT, padx=5)

        separator = ttk.Separator(button_frame, orient=tk.VERTICAL)
        separator.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=0)

        set_active_btn = ttk.Button(button_frame, text="⭐ Set as Active", command=set_active)
        set_active_btn.pack(side=tk.LEFT, padx=5)

        # ===== TAB 2: STAFF MEMBERS =====
        staff_tab = ttk.Frame(notebook)
        notebook.add(staff_tab, text="👥 Staff Members")

        # Staff members treeview
        staff_frame = ttk.Frame(staff_tab)
        staff_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        staff_columns = ("Name", "Role")
        staff_tree = ttk.Treeview(staff_frame, columns=staff_columns, height=15, selectmode='extended')

        staff_tree.column("#0", width=0, stretch=tk.NO)
        staff_tree.column("Name", width=300)
        staff_tree.column("Role", width=200)

        staff_tree.heading("Name", text="Name")
        staff_tree.heading("Role", text="Role")

        staff_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        staff_scrollbar = ttk.Scrollbar(staff_frame, orient=tk.VERTICAL, command=staff_tree.yview)
        staff_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        staff_tree.configure(yscroll=staff_scrollbar.set)

        # Bind mousewheel events for scrolling
        def _on_staff_tree_mousewheel(event):
            if event.num == 4 or event.delta > 0:
                staff_tree.yview_scroll(-3, "units")
            elif event.num == 5 or event.delta < 0:
                staff_tree.yview_scroll(3, "units")

        staff_tree.bind("<MouseWheel>", _on_staff_tree_mousewheel)
        staff_tree.bind("<Button-4>", _on_staff_tree_mousewheel)
        staff_tree.bind("<Button-5>", _on_staff_tree_mousewheel)

        def populate_staff_tree():
            for item in staff_tree.get_children():
                staff_tree.delete(item)
            try:
                conn = sqlite3.connect(DB_FILE)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT id, name, role FROM staff_members ORDER BY name")
                for row in cursor.fetchall():
                    staff_tree.insert("", "end", iid=row['id'], values=(row['name'], row['role'] or ''))
                conn.close()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load staff: {e}")

        def add_staff():
            show_staff_edit_dialog(staff_id=None, parent_window=main_window)

        def edit_staff():
            selected = staff_tree.selection()
            if not selected:
                messagebox.showwarning("Warning", "Please select a staff member to edit.")
                return
            staff_id = int(selected[0])
            show_staff_edit_dialog(staff_id=staff_id, parent_window=main_window)

        def delete_staff():
            selected = staff_tree.selection()
            if not selected:
                messagebox.showwarning("Warning", "Please select a staff member to delete.")
                return

            if not messagebox.askyesno("Confirm Delete",
                f"Are you sure you want to permanently delete {len(selected)} staff member(s)?\n\nThis action cannot be undone."):
                return

            try:
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                for staff_id in selected:
                    cursor.execute("DELETE FROM staff_members WHERE id = ?", (int(staff_id),))
                conn.commit()
                conn.close()

                show_toast(f"Deleted {len(selected)} staff member(s)")
                refresh_staff_dropdowns()
                populate_staff_tree()

            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete staff: {e}")

        def on_staff_double_click(event):
            selected = staff_tree.selection()
            if selected:
                edit_staff()

        staff_tree.bind("<Double-1>", on_staff_double_click)

        # Staff buttons
        staff_button_frame = ttk.Frame(staff_tab)
        staff_button_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(staff_button_frame, text="➕ Add Staff", command=add_staff).pack(side=tk.LEFT, padx=5)
        ttk.Button(staff_button_frame, text="✏️ Edit", command=edit_staff).pack(side=tk.LEFT, padx=5)
        ttk.Button(staff_button_frame, text="🗑️ Delete", command=delete_staff).pack(side=tk.LEFT, padx=5)

        # Populate staff tree on load
        populate_staff_tree()

    except Exception as e:
        messagebox.showerror("Error", f"Failed to open Inventory & Staff: {e}")


def import_stock_csv_dialog():
    """Open file dialog to select CSV file for import."""
    csv_file = filedialog.askopenfilename(
        initialdir=WORKING_DIR,
        title="Select Stock CSV File",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
    )
    
    if csv_file:
        import_stock_csv(csv_file)


def update_allergen_options(*args):
    """Updates the visible allergen checkboxes based on vial type and loads the prescription for that type."""
    global last_vials, last_prescription_data, last_compounding_log_id, prescription_generated
    mode = vial_type_var.get()
    print(f"DEBUG: update_allergen_options called, switching to: {mode}")

    if mode == "Environmental":
        for frame in venom_allergen_frames:
            frame.grid_remove()
        for frame in environmental_allergen_frames:
            frame.grid()

    elif mode == "Venom":
        for frame in environmental_allergen_frames:
            frame.grid_remove()
        for frame in venom_allergen_frames:
            frame.grid()

    else:
        for frame in environmental_allergen_frames:
            frame.grid_remove()
        for frame in venom_allergen_frames:
            frame.grid_remove()

    # Load prescription for the newly selected vial_type if a patient is loaded
    print(f"DEBUG: last_prescription_data exists: {bool(last_prescription_data)}, has MRN: {bool(last_prescription_data and last_prescription_data.get('mrn'))}")
    if last_prescription_data and last_prescription_data.get('mrn'):
        conn = None
        try:
            print(f"DEBUG: update_allergen_options - opening DB connection")
            conn = sqlite3.connect(DB_FILE, timeout=15)
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM patients WHERE mrn = ?", (last_prescription_data['mrn'],))
            result = cursor.fetchone()

            if result:
                patient_id = result[0]
                vials, loaded_vial_type, loaded_treatment_type = load_prescription_from_database(patient_id, mode)
                print(f"DEBUG: Loaded prescription for {mode}: vials={len(vials) if vials else 0}, type={loaded_vial_type}")

                if vials:
                    last_vials = vials
                    last_prescription_data['vial_type'] = loaded_vial_type
                    last_prescription_data['treatment_type'] = loaded_treatment_type

                    # Update treatment type dropdown
                    if treatment_type_var:
                        treatment_type_var.set(loaded_treatment_type or "New Start")

                    # Update allergen checkboxes based on loaded vials
                    # Clear all checkboxes first
                    for var in environmental_allergen_vars.values():
                        var.set(False)
                    for var in venom_allergen_vars.values():
                        var.set(False)

                    # Check boxes for allergens in loaded vials
                    for vial in vials:
                        for allergen_name in vial.allergens.keys():
                            if allergen_name != "HSA Diluent":
                                if allergen_name in environmental_allergen_vars:
                                    environmental_allergen_vars[allergen_name].set(True)
                                elif allergen_name in venom_allergen_vars:
                                    venom_allergen_vars[allergen_name].set(True)


                    # TODO: Don't create compounding log during load/switch - create on-demand when printing
                    # if patient_id:
                    #     last_compounding_log_id = create_compounding_log_with_retry(...)

                    # Display the loaded prescription
                    display_prescription_output(last_vials, last_prescription_data, loaded_vial_type)
                    prescription_generated = True
                # If no prescription found, don't clear last_vials - user may want to generate a new one
        except Exception as e:
            print(f"Warning: Could not load prescription for {mode}: {e}")
        finally:
            if conn:
                print(f"DEBUG: update_allergen_options - closing DB connection")
                conn.close()
                print(f"DEBUG: update_allergen_options - connection closed")



def on_selection_changed(*args):
    """Called when any allergen or treatment option changes. Marks prescription as stale."""
    global prescription_generated
    if prescription_generated:
        prescription_generated = False
        # Only update display if result_label exists (during UI operation)
        if 'result_label' in globals():
            result_label.config(text="⚠️ PRESCRIPTION OUTDATED\n\nAllergen selections have changed. Click Generate to create an updated prescription.", fg="#d97706")


def save_current_patient():
    """Save current patient data without clearing the form."""
    patient_name = patient_name_entry.get().strip()
    mrn = mrn_entry.get().strip()

    if not patient_name or not mrn:
        messagebox.showerror("Error", "Please enter patient name and MRN before saving.")
        return

    try:
        dob = normalize_two_digit_year(dob_entry.get_date())
        address = address_entry.get().strip()
        city = city_entry.get().strip()
        state = state_entry.get().strip()
        zip_code = zip_entry.get().strip()
        phone = phone_entry.get().strip()
        treatment_type = treatment_type_var.get()

        # Get selected allergens
        mode = vial_type_var.get()
        if mode == "Environmental":
            selected_allergens = [
                allergen for allergen, var in environmental_allergen_vars.items() if var.get()
            ]
        elif mode == "Venom":
            selected_allergens = [
                allergen for allergen, var in venom_allergen_vars.items() if var.get()
            ]
        else:
            selected_allergens = []

        selected_allergens_str = ", ".join(selected_allergens) if selected_allergens else ""

        patient_data = {
            'patient_name': patient_name,
            'dob': dob,
            'mrn': mrn,
            'address': address,
            'city': city,
            'state': state,
            'zip_code': zip_code,
            'phone': phone,
            'treatment_type': treatment_type
        }

        # Save the patient
        save_patient_data(patient_data, selected_allergens_str)
    except ValueError:
        messagebox.showerror("Error", "Invalid date of birth entered.")
    except Exception as e:
        messagebox.showerror("Error", f"Could not save patient data: {e}")


def new_patient():
    """Save current patient (if any data entered) and start fresh with new patient."""
    patient_name = patient_name_entry.get().strip()
    mrn = mrn_entry.get().strip()

    # Only save if patient has name and MRN
    if patient_name and mrn:
        try:
            dob = normalize_two_digit_year(dob_entry.get_date())
            address = address_entry.get().strip()
            city = city_entry.get().strip()
            state = state_entry.get().strip()
            zip_code = zip_entry.get().strip()
            phone = phone_entry.get().strip()
            treatment_type = treatment_type_var.get()

            # Get selected allergens
            mode = vial_type_var.get()
            if mode == "Environmental":
                selected_allergens = [
                    allergen for allergen, var in environmental_allergen_vars.items() if var.get()
                ]
            elif mode == "Venom":
                selected_allergens = [
                    allergen for allergen, var in venom_allergen_vars.items() if var.get()
                ]
            else:
                selected_allergens = []

            selected_allergens_str = ", ".join(selected_allergens) if selected_allergens else ""

            patient_data = {
                'patient_name': patient_name,
                'dob': dob,
                'mrn': mrn,
                'address': address,
                'city': city,
                'state': state,
                'zip_code': zip_code,
                'phone': phone,
                'treatment_type': treatment_type
            }

            # Save the patient
            save_patient_data(patient_data, selected_allergens_str)
        except Exception as e:
            messagebox.showwarning("Save Warning", f"Could not save current patient data: {e}")

    # Clear all fields for new patient
    clear_fields()


def clear_fields():
    """Clears all input fields and checkbox selections."""
    global prescription_generated
    patient_name_entry.delete(0, tk.END)
    dob_entry.set_date(datetime.date.today())
    mrn_entry.delete(0, tk.END)
    address_entry.delete(0, tk.END)
    city_entry.delete(0, tk.END)
    city_entry.insert(0, "Cincinnati")  # Auto-populate city
    state_entry.delete(0, tk.END)
    state_entry.insert(0, "OH")  # Auto-populate state
    zip_entry.delete(0, tk.END)
    phone_entry.delete(0, tk.END)
    # Uncheck all checkboxes
    for var in environmental_allergen_vars.values():
        var.set(False)
    for var in venom_allergen_vars.values():
        var.set(False)
    # Reset treatment type to New Start
    treatment_type_var.set("New Start")
    if allow_fourth_vial_var:
        allow_fourth_vial_var.set(False)
    result_label.config(text="", fg=TEXT_COLOR)  # Clear result label
    prescription_generated = False
    # Scroll left canvas to top for easier demographics entry
    left_canvas.yview_moveto(0)


def cleanup_old_backups():
    """Delete backup databases older than 6 months."""
    try:
        from pathlib import Path
        import datetime
        import os

        db_path = Path(DB_FILE)
        backup_dir = db_path.parent / "backups"

        if not backup_dir.exists():
            return

        # Calculate cutoff date (6 months ago)
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=180)

        deleted_count = 0
        for backup_file in backup_dir.glob("*.db"):
            # Get file modification time
            file_mtime = datetime.datetime.fromtimestamp(os.path.getmtime(backup_file))

            if file_mtime < cutoff_date:
                try:
                    backup_file.unlink()
                    deleted_count += 1
                    print(f"Deleted old backup: {backup_file.name}")
                except Exception as e:
                    print(f"Warning: Could not delete backup {backup_file.name}: {e}")

        if deleted_count > 0:
            print(f"Cleanup: Deleted {deleted_count} backup(s) older than 6 months")

    except Exception as e:
        print(f"Warning: Could not cleanup old backups: {e}")


def backup_database():
    """Create a timestamped backup of the database in a 'backups' folder."""
    try:
        db_path = Path(DB_FILE)
        backup_dir = db_path.parent / "backups"

        # Create backups folder if it doesn't exist
        backup_dir.mkdir(exist_ok=True)

        # Generate timestamp for backup filename
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{db_path.stem}_backup_{timestamp}.db"
        backup_path = backup_dir / backup_filename

        # Copy database file to backup location
        import shutil
        shutil.copy2(str(db_path), str(backup_path))
        print(f"Database backed up to: {backup_path}")
    except Exception as e:
        print(f"Warning: Could not create database backup: {e}")


def on_closing():
    """Handle application closing - backup database and exit."""
    try:
        backup_database()
    except Exception as e:
        print(f"Backup error: {e}")
    finally:
        root.destroy()


def find_and_show_duplicates():
    """Find duplicate patients and show in a dialog for merging."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # Find patients with same normalized MRN and name
        cursor.execute("""
            SELECT id, patient_name, mrn FROM patients
            ORDER BY patient_name, mrn
        """)
        all_patients = cursor.fetchall()
        conn.close()

        # Group by normalized MRN and name
        duplicates = {}
        for patient_id, name, mrn in all_patients:
            normalized_key = (name.strip().lower(), mrn.strip().lower())
            if normalized_key not in duplicates:
                duplicates[normalized_key] = []
            duplicates[normalized_key].append((patient_id, name, mrn))

        # Find groups with more than one patient
        duplicate_groups = {k: v for k, v in duplicates.items() if len(v) > 1}

        if not duplicate_groups:
            messagebox.showinfo("No Duplicates", "No duplicate patients found in the database.")
            return

        # Show duplicates in a new window
        dup_window = tk.Toplevel(root)
        dup_window.title("Duplicate Patients Found")
        dup_window.geometry("700x550")

        tk.Label(dup_window, text=f"Found {len(duplicate_groups)} duplicate groups:", font=("Arial", 12, "bold")).pack(pady=10)

        frame = ttk.Frame(dup_window)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        canvas = tk.Canvas(frame, bg="white")
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Display each duplicate group
        for (norm_name, norm_mrn), patients in duplicate_groups.items():
            group_frame = ttk.LabelFrame(scrollable_frame, text=f"Group: {patients[0][1]} (MRN variations)", padding=10)
            group_frame.pack(fill=tk.X, padx=5, pady=5)

            for patient_id, name, mrn in patients:
                record_text = f"ID {patient_id}: {name} | MRN: {mrn}"
                record_frame = ttk.Frame(group_frame)
                record_frame.pack(fill=tk.X, pady=3)

                tk.Label(record_frame, text=record_text, font=("Arial", 10)).pack(side=tk.LEFT, expand=True, anchor="w")

                # Create merge button
                def make_merge_callback(keep_id, delete_id, delete_name):
                    def merge_callback():
                        if merge_patient_records(keep_id, delete_id):
                            dup_window.destroy()
                            messagebox.showinfo("Success", f"Merged and deleted duplicate. Kept patient record for {delete_name}.")
                            # Refresh the patient list
                            load_patient_list()
                    return merge_callback

                # For each patient, offer to merge with the first one
                if patient_id != patients[0][0]:
                    merge_btn = ttk.Button(
                        record_frame,
                        text="Delete This (Keep First)",
                        command=make_merge_callback(patients[0][0], patient_id, patients[0][1])
                    )
                    merge_btn.pack(side=tk.RIGHT, padx=5)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Button frame at bottom
        button_frame = ttk.Frame(dup_window)
        button_frame.pack(fill=tk.X, padx=10, pady=10)

        def merge_all_smart():
            """Merge all duplicates, keeping the patient with prescriptions."""
            try:
                merged_count = 0
                for (norm_name, norm_mrn), patients in duplicate_groups.items():
                    # Find which patient has prescriptions
                    keep_id = None
                    for patient_id, _, _ in patients:
                        if patient_has_prescriptions(patient_id):
                            keep_id = patient_id
                            break

                    # If no patient has prescriptions, keep the first (lowest ID)
                    if keep_id is None:
                        keep_id = min(p[0] for p in patients)

                    # Merge all others into keep_id
                    for patient_id, patient_name, _ in patients:
                        if patient_id != keep_id:
                            if merge_patient_records(keep_id, patient_id, show_confirmation=False):
                                merged_count += 1

                dup_window.destroy()
                messagebox.showinfo("Merge Complete", f"Successfully merged {merged_count} duplicate records.")
                load_patient_list()
            except Exception as e:
                messagebox.showerror("Merge Error", f"Error merging duplicates: {e}")

        merge_all_btn = ttk.Button(button_frame, text="Merge All Duplicates", command=merge_all_smart)
        merge_all_btn.pack(side=tk.LEFT, padx=5)

        # Add info label
        info_text = "Use 'Merge All Duplicates' to automatically merge all groups (keeps record with prescriptions). Or manually delete duplicates below."
        tk.Label(dup_window, text=info_text, font=("Arial", 9), wraplength=650, justify=tk.LEFT, fg="#555555").pack(padx=10, pady=10)

    except Exception as e:
        messagebox.showerror("Error", f"Could not find duplicates: {e}")


def patient_has_prescriptions(patient_id):
    """Check if a patient has any saved prescriptions."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM patient_prescriptions WHERE patient_id = ?", (patient_id,))
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


def merge_patient_records(keep_id, delete_id, show_confirmation=True):
    """Merge two patient records, keeping keep_id and deleting delete_id.

    Transfers all prescriptions and compounding logs from delete_id to keep_id.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # First, get the name of the patient being deleted (for confirmation)
        cursor.execute("SELECT patient_name FROM patients WHERE id = ?", (delete_id,))
        result = cursor.fetchone()
        delete_name = result[0] if result else "Unknown"

        # Confirm the merge with user (unless auto-merging)
        if show_confirmation:
            confirm = messagebox.askyesno(
                "Confirm Merge",
                f"Keep: ID {keep_id}\nDelete: ID {delete_id} ({delete_name})\n\n"
                f"This will:\n"
                f"- Transfer all prescriptions to the kept record\n"
                f"- Transfer all compounding logs to the kept record\n"
                f"- Permanently delete the duplicate patient record\n\n"
                f"This action cannot be undone!"
            )
        else:
            confirm = True

        if not confirm:
            return False

        # Transfer patient_prescriptions
        cursor.execute("""
            UPDATE patient_prescriptions
            SET patient_id = ?
            WHERE patient_id = ?
        """, (keep_id, delete_id))

        # Transfer compounding_logs
        cursor.execute("""
            UPDATE compounding_logs
            SET patient_id = ?
            WHERE patient_id = ?
        """, (keep_id, delete_id))

        # Delete the duplicate patient record
        cursor.execute("DELETE FROM patients WHERE id = ?", (delete_id,))

        conn.commit()
        conn.close()

        print(f"Successfully merged patient {delete_id} into {keep_id}")
        return True

    except Exception as e:
        messagebox.showerror("Merge Error", f"Could not merge patients: {e}")
        return False

# Check for first launch and get database location if needed
handle_first_launch()

# Initialize database
init_database()

root = tk.Tk()
root.title(f"Allergen Immunotherapy Prescription Generator by Yashu Dhamija MD 2026 version {APP_VERSION}")
root.geometry("1800x900")

# --- Create Menu Bar ---
menubar = tk.Menu(root)
root.config(menu=menubar)

file_menu = tk.Menu(menubar, tearoff=0)
menubar.add_cascade(label="File", menu=file_menu)
file_menu.add_command(label="Save", command=save_current_patient, accelerator="Alt+S")
file_menu.add_command(label="New Patient", command=new_patient, accelerator="Alt+X")
file_menu.add_separator()
file_menu.add_command(label="Find Duplicates", command=find_and_show_duplicates)
file_menu.add_separator()
file_menu.add_command(label="Settings", command=open_settings, accelerator="Alt+E")
file_menu.add_command(label="Dose Ranges", command=open_dose_ranges_window, accelerator="Alt+D")
file_menu.add_separator()
file_menu.add_command(label="Exit", command=root.quit)

# Bind keyboard shortcuts
root.bind("<Alt-s>", lambda e: save_current_patient())
root.bind("<Alt-x>", lambda e: new_patient())
root.bind("<Alt-e>", lambda e: open_settings())
root.bind("<Alt-d>", lambda e: open_dose_ranges_window())

# Configure modern color scheme
BG_COLOR = "#f0f2f5"
HEADER_COLOR = "#1f77d2"
ACCENT_COLOR = "#0d5bba"
TEXT_COLOR = "#2c3e50"
SECTION_BG = "#ffffff"

root.configure(bg=BG_COLOR)

# Configure custom styles
style = ttk.Style()
style.theme_use('clam')
style.configure('Header.TLabel', font=('Segoe UI', 14, 'bold'), foreground=HEADER_COLOR)
style.configure('Subheader.TLabel', font=('Segoe UI', 11, 'bold'), foreground=TEXT_COLOR)
style.configure('TLabel', font=('Segoe UI', 10), background=BG_COLOR, foreground=TEXT_COLOR)
style.configure('TLabelframe', font=('Segoe UI', 10, 'bold'), background=BG_COLOR, foreground=TEXT_COLOR)
style.configure('TLabelframe.Label', font=('Segoe UI', 10, 'bold'), background=BG_COLOR, foreground=HEADER_COLOR)
style.configure('TButton', font=('Segoe UI', 10, 'bold'))
style.configure('TCombobox', font=('Segoe UI', 10))
style.map('TButton', 
          background=[('active', ACCENT_COLOR)],
          foreground=[('active', 'white')])

# Add title at the top
title_frame = tk.Frame(root, bg=HEADER_COLOR, height=60)
title_frame.pack(side=tk.TOP, fill=tk.X, padx=0, pady=0)
title_label = tk.Label(title_frame, text="Allergy Shot Vial Prescription Generator by Yashu Dhamija MD", 
                       font=('Segoe UI', 16, 'bold'), bg=HEADER_COLOR, fg='white')
title_label.pack(pady=10)

# --- Main content frame with two columns ---
content_frame = ttk.Frame(root)
content_frame.pack(fill=tk.BOTH, expand=1)

# --- LEFT SIDE: Input Form (Scrollable) ---
left_frame = ttk.Frame(content_frame)
left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=1)

# Define mousewheel handlers before creating bindings
def _on_mousewheel_left(event):
    """Handle mouse wheel scroll on left canvas. Supports both MouseWheel and Button scroll events."""
    if event.num == 4 or event.delta > 0:
        left_canvas.yview_scroll(-1, "units")
    elif event.num == 5 or event.delta < 0:
        left_canvas.yview_scroll(1, "units")
    else:
        left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

def _on_mousewheel_right(event):
    """Handle mouse wheel scroll on right canvas. Supports both MouseWheel and Button scroll events."""
    if event.num == 4 or event.delta > 0:
        right_canvas.yview_scroll(-1, "units")
    elif event.num == 5 or event.delta < 0:
        right_canvas.yview_scroll(1, "units")
    else:
        right_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

left_canvas = tk.Canvas(left_frame, bg=BG_COLOR, highlightthickness=0)
left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=1)

left_scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=left_canvas.yview)
left_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

left_canvas.configure(yscrollcommand=left_scrollbar.set)

# Form frame inside left canvas
form_frame = ttk.Frame(left_canvas, style='')
left_window_id = left_canvas.create_window((0, 0), window=form_frame, anchor="nw")

# Keep scrollregion and frame width in sync with canvas size
left_canvas.bind(
    '<Configure>',
    lambda e: (
        left_canvas.itemconfigure(left_window_id, width=e.width),
        left_canvas.configure(scrollregion=left_canvas.bbox("all"))
    )
)
form_frame.bind('<Configure>', lambda e: left_canvas.configure(scrollregion=left_canvas.bbox("all")))

# Mousewheel scrolling for left canvas - support both MouseWheel and alternative scroll events
left_canvas.bind("<Enter>", lambda e: (
    left_canvas.bind_all("<MouseWheel>", _on_mousewheel_left),
    left_canvas.bind_all("<Button-4>", _on_mousewheel_left),
    left_canvas.bind_all("<Button-5>", _on_mousewheel_left)
))
left_canvas.bind("<Leave>", lambda e: (
    left_canvas.unbind_all("<MouseWheel>"),
    left_canvas.unbind_all("<Button-4>"),
    left_canvas.unbind_all("<Button-5>")
))

# --- RIGHT SIDE: Prescription Output (Scrollable) ---
right_frame = ttk.Frame(content_frame)
right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=1)

right_canvas = tk.Canvas(right_frame, bg=BG_COLOR, highlightthickness=0)
right_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=1)

right_scrollbar = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=right_canvas.yview)
right_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

right_canvas.configure(yscrollcommand=right_scrollbar.set)

# Output frame inside right canvas
output_frame = ttk.Frame(right_canvas, style='')
right_window_id = right_canvas.create_window((0, 0), window=output_frame, anchor="nw")

# Keep scrollregion and frame width in sync with canvas size
right_canvas.bind(
    '<Configure>',
    lambda e: (
        right_canvas.itemconfigure(right_window_id, width=e.width),
        right_canvas.configure(scrollregion=right_canvas.bbox("all"))
    )
)
output_frame.bind('<Configure>', lambda e: right_canvas.configure(scrollregion=right_canvas.bbox("all")))

# Mousewheel scrolling for right canvas - support both MouseWheel and alternative scroll events
right_canvas.bind("<Enter>", lambda e: (
    right_canvas.bind_all("<MouseWheel>", _on_mousewheel_right),
    right_canvas.bind_all("<Button-4>", _on_mousewheel_right),
    right_canvas.bind_all("<Button-5>", _on_mousewheel_right)
))
right_canvas.bind("<Leave>", lambda e: (
    right_canvas.unbind_all("<MouseWheel>"),
    right_canvas.unbind_all("<Button-4>"),
    right_canvas.unbind_all("<Button-5>")
))

# Configure form_frame columns
form_frame.columnconfigure(0, weight=1)

# --- Patient Information ---
patient_info_frame = ttk.LabelFrame(form_frame, text="Patient Information")
patient_info_frame.grid(row=0, column=0, padx=8, pady=8, sticky="ew")

# Patient Name
patient_name_label = ttk.Label(patient_info_frame, text="Patient Name:", style='Subheader.TLabel')
patient_name_label.grid(row=0, column=0, padx=6, pady=4, sticky="w")
patient_name_entry = ttk.Entry(patient_info_frame, width=40)
patient_name_entry.grid(row=0, column=1, padx=6, pady=4, sticky="ew")

# Date of Birth
dob_label = ttk.Label(patient_info_frame, text="Date of Birth:", style='Subheader.TLabel')
dob_label.grid(row=1, column=0, padx=6, pady=4, sticky="w")
dob_entry = DateEntry(patient_info_frame, width=12, background=HEADER_COLOR, foreground='white',
                      borderwidth=2, date_pattern='m-d-Y')
dob_entry.grid(row=1, column=1, padx=6, pady=4, sticky="ew")

# Medical Record Number
mrn_label = ttk.Label(patient_info_frame, text="MRN:", style='Subheader.TLabel')
mrn_label.grid(row=2, column=0, padx=6, pady=4, sticky="w")
mrn_entry = ttk.Entry(patient_info_frame, width=40)
mrn_entry.grid(row=2, column=1, padx=6, pady=4, sticky="ew")

# Street Address
address_label = ttk.Label(patient_info_frame, text="Street Address:", style='Subheader.TLabel')
address_label.grid(row=3, column=0, padx=6, pady=4, sticky="w")
address_entry = ttk.Entry(patient_info_frame, width=40)
address_entry.grid(row=3, column=1, padx=6, pady=4, sticky="ew")

# City
city_label = ttk.Label(patient_info_frame, text="City:", style='Subheader.TLabel')
city_label.grid(row=4, column=0, padx=6, pady=4, sticky="w")
city_entry = ttk.Entry(patient_info_frame, width=40)
city_entry.grid(row=4, column=1, padx=6, pady=4, sticky="ew")

# State
state_label = ttk.Label(patient_info_frame, text="State:", style='Subheader.TLabel')
state_label.grid(row=5, column=0, padx=6, pady=4, sticky="w")
state_entry = ttk.Entry(patient_info_frame, width=40)
state_entry.grid(row=5, column=1, padx=6, pady=4, sticky="ew")

# Zip Code
zip_label = ttk.Label(patient_info_frame, text="Zip Code:", style='Subheader.TLabel')
zip_label.grid(row=6, column=0, padx=6, pady=4, sticky="w")
zip_entry = ttk.Entry(patient_info_frame, width=40)
zip_entry.grid(row=6, column=1, padx=6, pady=4, sticky="ew")

# Phone Number
phone_label = ttk.Label(patient_info_frame, text="Phone Number:", style='Subheader.TLabel')
phone_label.grid(row=7, column=0, padx=6, pady=4, sticky="w")
phone_entry = ttk.Entry(patient_info_frame, width=40)
phone_entry.grid(row=7, column=1, padx=6, pady=4, sticky="ew")

patient_info_frame.columnconfigure(1, weight=1)

# --- Vial Type Selection ---
controls_frame = ttk.Frame(form_frame)
controls_frame.grid(row=8, column=0, padx=8, pady=6, sticky="ew")

vial_type_label = ttk.Label(controls_frame, text="Vial Type:", style='Subheader.TLabel')
vial_type_label.pack(side=tk.LEFT, padx=5)

vial_type_var = tk.StringVar(value="Environmental")
vial_type_var.trace_add("write", update_allergen_options)
vial_type_var.trace_add("write", on_selection_changed)

vial_type_combo = ttk.Combobox(controls_frame, textvariable=vial_type_var,
                               values=["Environmental", "Venom"], state='readonly', width=20)
vial_type_combo.pack(side=tk.LEFT, padx=5)

# --- Treatment Type Selection and Load Patient Button ---
treatment_label = ttk.Label(controls_frame, text="Treatment Type:", style='Subheader.TLabel')
treatment_label.pack(side=tk.LEFT, padx=(15, 5))

treatment_type_var = tk.StringVar(value="New Start")
treatment_type_var.trace_add("write", on_selection_changed)
treatment_combo = ttk.Combobox(controls_frame, textvariable=treatment_type_var,
                               values=["New Start", "Maintenance"], state='readonly', width=20)
treatment_combo.pack(side=tk.LEFT, padx=5)

allow_fourth_vial_var = tk.BooleanVar(value=False)
allow_fourth_vial_var.trace_add("write", on_selection_changed)
fourth_vial_check = ttk.Checkbutton(controls_frame, text="4th Vial?", variable=allow_fourth_vial_var)
fourth_vial_check.pack(side=tk.LEFT, padx=(10, 5))

# --- Prescriber / Prepared By / Load Patient ---
prescriber_frame = ttk.Frame(form_frame)
prescriber_frame.grid(row=9, column=0, padx=8, pady=6, sticky="ew")

prescriber_label = ttk.Label(prescriber_frame, text="Prescriber:", style='Subheader.TLabel')
prescriber_label.pack(side=tk.LEFT, padx=5)

prescriber_var = tk.StringVar(value="Yashu Dhamija MD")
prescriber_combo = ttk.Combobox(
    prescriber_frame,
    textvariable=prescriber_var,
    values=["Yashu Dhamija MD", "Joshua Bernstein MD"],
    state='readonly',
    width=25
)
prescriber_combo.pack(side=tk.LEFT, padx=5)

mix_preparer_label = ttk.Label(prescriber_frame, text="Prepared By:", style='Subheader.TLabel')
mix_preparer_label.pack(side=tk.LEFT, padx=(15, 5))

mix_preparer_var = tk.StringVar(value="Elaine Sturtevant RN")
mix_preparer_combo = ttk.Combobox(
    prescriber_frame,
    textvariable=mix_preparer_var,
    values=["Yashu Dhamija MD", "Elaine Sturtevant RN"],
    state='readonly',
    width=25
)
mix_preparer_combo.pack(side=tk.LEFT, padx=5)

load_patient_button = ttk.Button(prescriber_frame, text="📁 Load Patient", command=load_patient)
load_patient_button.pack(side=tk.RIGHT, padx=5)

# --- Helper function for allergen groups ---
def create_allergen_group(parent_frame, allergens_list, allergen_vars_dict, on_change_callback):
    """
    Create allergen checkboxes with clickable labels and a "Check All" button.

    Args:
        parent_frame: The LabelFrame to add allergens to
        allergens_list: List of allergen names
        allergen_vars_dict: Dictionary to store BooleanVar objects
        on_change_callback: Function to call when selection changes
    """
    # Add "Check All / Clear All" button at the top
    button_frame = ttk.Frame(parent_frame)
    button_frame.grid(row=0, column=0, columnspan=1, padx=6, pady=3, sticky="ew")

    def check_all():
        for var in [allergen_vars_dict[allergen] for allergen in allergens_list]:
            var.set(True)

    def clear_all():
        for var in [allergen_vars_dict[allergen] for allergen in allergens_list]:
            var.set(False)

    ttk.Button(button_frame, text="✓ Check All", command=check_all, width=12).pack(side=tk.LEFT, padx=2)
    ttk.Button(button_frame, text="✗ Clear All", command=clear_all, width=12).pack(side=tk.LEFT, padx=2)

    # Create allergen checkboxes with clickable labels - single column layout
    for i, allergen in enumerate(allergens_list):
        var = tk.BooleanVar()
        allergen_vars_dict[allergen] = var
        var.trace_add("write", on_change_callback)

        # Create a frame to hold checkbox and label together
        check_frame = ttk.Frame(parent_frame)
        check_frame.grid(row=i + 1, column=0, padx=6, pady=3, sticky="w")

        # Create checkbox
        checkbox = ttk.Checkbutton(check_frame, variable=var)
        checkbox.pack(side=tk.LEFT)

        # Create clickable label
        label = tk.Label(check_frame, text=allergen, cursor="hand2", bg=BG_COLOR, fg=TEXT_COLOR)
        label.pack(side=tk.LEFT, padx=(2, 0))

        # Bind label click to toggle checkbox
        def toggle_allergen(event, var=var):
            var.set(not var.get())

        label.bind("<Button-1>", toggle_allergen)

# --- Environmental Allergen Checkboxes ---
environmental_allergen_frames = []
environmental_allergen_vars = {}

# --- Mold Group ---
mold_frame = ttk.LabelFrame(form_frame, text="🌱 Mold")
mold_frame.grid(row=10, column=0, padx=8, pady=6, sticky="ew")
environmental_allergen_frames.append(mold_frame)
mold_allergens = ["Alternaria", "Aspergillus", "Cladosporium", "Penicillium"]
create_allergen_group(mold_frame, mold_allergens, environmental_allergen_vars, on_selection_changed)

# --- Tree Group ---
tree_frame = ttk.LabelFrame(form_frame, text="🌳 Tree")
tree_frame.grid(row=11, column=0, padx=8, pady=6, sticky="ew")
environmental_allergen_frames.append(tree_frame)
tree_allergens = ["Ash", "Cedar", "Hackberry (Elm)", "Maple", "Birch (Oak)", "Sycamore", "Walnut (Pecan)",
                  "Willow (Cottonwood)", "Mulberry"]
create_allergen_group(tree_frame, tree_allergens, environmental_allergen_vars, on_selection_changed)

# --- Grass Group ---
grass_frame = ttk.LabelFrame(form_frame, text="🌾 Grass")
grass_frame.grid(row=12, column=0, padx=8, pady=6, sticky="ew")
environmental_allergen_frames.append(grass_frame)
grass_allergens = ["Bermuda", "Johnson", "Timothy"]
create_allergen_group(grass_frame, grass_allergens, environmental_allergen_vars, on_selection_changed)

# --- Weed Group ---
weed_frame = ttk.LabelFrame(form_frame, text="🌿 Weed")
weed_frame.grid(row=13, column=0, padx=8, pady=6, sticky="ew")
environmental_allergen_frames.append(weed_frame)
weed_allergens = ["Cocklebur", "Yellow Dock (Sheep Sorrel)", "Kochia (Burning Bush)", "Lamb's Quarter", "Russian Thistle",
                  "Mugwort", "Pigweed", "English Plantain", "Ragweed"]
create_allergen_group(weed_frame, weed_allergens, environmental_allergen_vars, on_selection_changed)

# --- Other Group ---
other_frame = ttk.LabelFrame(form_frame, text="🐾 Other")
other_frame.grid(row=14, column=0, padx=8, pady=6, sticky="ew")
environmental_allergen_frames.append(other_frame)
other_allergens = ["Cat", "Dog - Epithelium", "Dog - UF", "Mouse", "Rat", "Horse", "Amer. Cockroach", "Ger. Cockroach",
                   "Dust Mite Mix"]
create_allergen_group(other_frame, other_allergens, environmental_allergen_vars, on_selection_changed)

# Add trace callbacks for dog extract mutual exclusivity
environmental_allergen_vars["Dog - UF"].trace_add("write", enforce_dog_mutual_exclusivity)
environmental_allergen_vars["Dog - Epithelium"].trace_add("write", enforce_dog_mutual_exclusivity)

# --- Venom Allergen Checkboxes ---
venom_allergen_frame = ttk.LabelFrame(form_frame, text="🐝 Venom Allergens")
venom_allergen_frame.grid(row=15, column=0, columnspan=2, padx=8, pady=6, sticky="ew")

venom_allergens = ["Honey Bee", "Yellow Jacket", "Yellow Faced Hornet", "White Faced Hornet", "Wasp"]
venom_allergen_vars = {}
venom_allergen_checkboxes = []
venom_allergen_frames = []  # Store frames for proper grid management

# Add "Check All / Clear All" button at the top
venom_button_frame = ttk.Frame(venom_allergen_frame)
venom_button_frame.grid(row=0, column=0, columnspan=2, padx=6, pady=3, sticky="ew")

def check_all_venom():
    for var in venom_allergen_vars.values():
        var.set(True)

def clear_all_venom():
    for var in venom_allergen_vars.values():
        var.set(False)

ttk.Button(venom_button_frame, text="✓ Check All", command=check_all_venom, width=12).pack(side=tk.LEFT, padx=2)
ttk.Button(venom_button_frame, text="✗ Clear All", command=clear_all_venom, width=12).pack(side=tk.LEFT, padx=2)

# Create venom allergen checkboxes with clickable labels
for i, allergen in enumerate(venom_allergens):
    var = tk.BooleanVar()
    venom_allergen_vars[allergen] = var
    var.trace_add("write", on_selection_changed)

    # Create a frame to hold checkbox and label together - single column layout
    check_frame = ttk.Frame(venom_allergen_frame)
    check_frame.grid(row=i + 1, column=0, padx=6, pady=3, sticky="w")

    # Create checkbox
    checkbox = ttk.Checkbutton(check_frame, variable=var)
    checkbox.pack(side=tk.LEFT)
    venom_allergen_checkboxes.append(checkbox)
    venom_allergen_frames.append(check_frame)  # Store frame for grid management

    # Create clickable label
    label = tk.Label(check_frame, text=allergen, cursor="hand2", bg=BG_COLOR, fg=TEXT_COLOR)
    label.pack(side=tk.LEFT, padx=(2, 0))

    # Bind label click to toggle checkbox
    def toggle_allergen_venom(event, var=var):
        var.set(not var.get())

    label.bind("<Button-1>", toggle_allergen_venom)

# Initially hide venom allergens
for widget in venom_allergen_frame.winfo_children():
    widget.grid_remove()

# --- Generate, Clear and Export PDF Buttons (Row 1) ---
button_frame1 = ttk.Frame(form_frame)
button_frame1.grid(row=16, column=0, padx=8, pady=4, sticky="ew")

generate_button = ttk.Button(button_frame1, text="✓ Generate", command=generate_prescription)
generate_button.pack(side=tk.LEFT, padx=3, ipadx=10, ipady=5)

clear_button = ttk.Button(button_frame1, text="⟲ Clear", command=clear_fields)
clear_button.pack(side=tk.LEFT, padx=3, ipadx=10, ipady=5)

stock_mgmt_button = ttk.Button(button_frame1, text="⚙️ Inventory & Staff", command=show_inventory_and_staff)
stock_mgmt_button.pack(side=tk.LEFT, padx=3, ipadx=10, ipady=5)

edit_volumes_button = ttk.Button(button_frame1, text="✏️ Edit Volumes", command=edit_prescription_volumes)
edit_volumes_button.pack(side=tk.LEFT, padx=3, ipadx=10, ipady=5)

# --- Import Stock CSV, Stock Management, Print Compounding Log Buttons (Row 2) ---
button_frame2 = ttk.Frame(form_frame)
button_frame2.grid(row=17, column=0, padx=8, pady=4, sticky="ew")

# import_stock_csv_button = ttk.Button(button_frame2, text="📥 Import Stock CSV", command=import_stock_csv_dialog)
# import_stock_csv_button.pack(side=tk.LEFT, padx=3, ipadx=10, ipady=5)

export_pdf_button = ttk.Button(button_frame2, text="📄 Print Script", command=export_prescription_to_pdf)
export_pdf_button.pack(side=tk.LEFT, padx=3, ipadx=10, ipady=5)

print_comp_log_button = ttk.Button(button_frame2, text="📋 Print Compounding Log", command=export_compounding_log_pdf)
print_comp_log_button.pack(side=tk.LEFT, padx=3, ipadx=10, ipady=5)

print_labels_button = ttk.Button(button_frame2, text="🏷 Print Labels", command=export_labels)
print_labels_button.pack(side=tk.LEFT, padx=3, ipadx=10, ipady=5)

# --- Expected Mix Date Selector ---
mix_date_frame = ttk.Frame(form_frame)
mix_date_frame.grid(row=18, column=0, padx=8, pady=8, sticky="ew")

tk.Label(mix_date_frame, text="Expected Mix Date:", font=("Arial", 10), bg=SECTION_BG).pack(side=tk.LEFT, padx=5)

global expected_mix_date_var
expected_mix_date_var = tk.StringVar()

class SmartDateEntry(DateEntry):
    """DateEntry that positions calendar above the date entry box."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bind("<Button-1>", self._on_click, add=True)

    def _on_click(self, event):
        """Store position info before calendar opens."""
        self._widget_x = self.winfo_rootx()
        self._widget_y = self.winfo_rooty()
        self._widget_height = self.winfo_height()
        # Let the normal click handler run
        self.after(100, self._move_calendar_up)

    def _move_calendar_up(self):
        """Move the calendar popup above the widget."""
        try:
            # Find the calendar Toplevel window
            for widget in root.winfo_children():
                if isinstance(widget, tk.Toplevel):
                    # This should be the calendar
                    widget.update_idletasks()
                    cal_height = widget.winfo_height()
                    cal_width = widget.winfo_width()

                    # Position above the entry box
                    new_y = self._widget_y - cal_height - 5
                    if new_y < 20:
                        new_y = 20

                    widget.geometry(f"+{self._widget_x}+{new_y}")
                    break
        except Exception as e:
            print(f"DEBUG: Failed to reposition calendar: {e}")

mix_date_picker = SmartDateEntry(mix_date_frame, textvariable=expected_mix_date_var, width=15,
                            date_pattern='mm/dd/yyyy')
mix_date_picker.pack(side=tk.LEFT, padx=5)
expected_mix_date_var.set(datetime.date.today().strftime("%m/%d/%Y"))

# --- Result Label with better styling ---
result_frame = tk.Frame(output_frame, bg=SECTION_BG, relief=tk.SUNKEN, bd=1)
result_frame.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")

result_title = tk.Label(result_frame, text="Prescription", font=('Segoe UI', 11, 'bold'),
                       bg=HEADER_COLOR, fg='white', anchor='w')
result_title.pack(fill=tk.X, padx=0, pady=0)

result_label = tk.Label(result_frame, text="Select Allergens and click Generate to create prescription", wraplength=700, justify=tk.LEFT,
                       font=('Courier New', 9), bg=SECTION_BG, fg=TEXT_COLOR,
                       anchor='nw', padx=10, pady=10)
result_label.pack(fill=tk.BOTH, expand=1, padx=0, pady=0)

# --- Expiring Extracts (Next 365 Days) ---
expiring_frame = tk.Frame(output_frame, bg=SECTION_BG, relief=tk.SUNKEN, bd=1)
expiring_frame.grid(row=1, column=0, padx=8, pady=8, sticky="nsew")

expiring_title = tk.Label(expiring_frame, text="Expiring Extracts (Next 365 Days)",
                          font=('Segoe UI', 11, 'bold'), bg=HEADER_COLOR, fg='white', anchor='w')
expiring_title.pack(fill=tk.X, padx=0, pady=0)

expiring_list_frame = ttk.Frame(expiring_frame)
expiring_list_frame.pack(fill=tk.BOTH, expand=1, padx=6, pady=6)

expiring_columns = ("Allergen", "Lot", "Expiration", "Active")
expiring_tree = ttk.Treeview(expiring_list_frame, columns=expiring_columns, height=10)
expiring_tree.column("#0", width=0, stretch=tk.NO)
expiring_col_widths = {"Allergen": 180, "Lot": 120, "Expiration": 110, "Active": 60}
for col in expiring_columns:
    expiring_tree.column(col, width=expiring_col_widths.get(col, 100))
    expiring_tree.heading(col, text=col)
expiring_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=1)

expiring_scrollbar = ttk.Scrollbar(expiring_list_frame, orient=tk.VERTICAL, command=expiring_tree.yview)
expiring_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
expiring_tree.configure(yscroll=expiring_scrollbar.set)

def refresh_expiring_extracts():
    for row_id in expiring_tree.get_children():
        expiring_tree.delete(row_id)

    try:
        # Use longer timeout for database operations (20 seconds)
        conn = sqlite3.connect(DB_FILE, timeout=20)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''
            SELECT allergen_name, lot_number, expiration_date, is_active
            FROM stock_extracts
            WHERE expiration_date IS NOT NULL AND expiration_date != ''
        ''')
        rows = cursor.fetchall()
        conn.close()

        today = datetime.datetime.now().date()
        cutoff = today + datetime.timedelta(days=365)
        filtered = []
        for row in rows:
            exp_date = parse_expiration_date(row['expiration_date'])
            if not exp_date:
                continue
            if today <= exp_date <= cutoff:
                filtered.append((row['allergen_name'], row['lot_number'], row['expiration_date'], row['is_active']))

        filtered.sort(key=lambda r: parse_expiration_date(r[2]) or datetime.date.max)

        for allergen_name, lot_number, expiration_date, is_active in filtered:
            expiring_tree.insert("", "end", values=(
                allergen_name,
                lot_number,
                expiration_date,
                "Yes" if is_active else "No"
            ))

    except sqlite3.OperationalError as e:
        if "database is locked" in str(e).lower():
            # Database is locked, skip this refresh and try again soon
            pass
        else:
            print(f"Warning: Failed to refresh expiring extracts list: {e}")
    except Exception as e:
        print(f"Warning: Failed to refresh expiring extracts list: {e}")

    # Schedule next refresh - skip quickly if database is locked
    root.after(5000, refresh_expiring_extracts)

# TODO: Temporarily disabled - causes database locking issues
refresh_expiring_extracts()

output_frame.columnconfigure(0, weight=1)
output_frame.rowconfigure(0, weight=1)
output_frame.rowconfigure(1, weight=0)

# --- Status Bar ---
status_frame = tk.Frame(root, bg="#e8eaed", height=30, relief=tk.SUNKEN, bd=1)
status_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=0, pady=0)
status_frame.pack_propagate(False)

is_connected, status_msg = check_database_connection()
status_color = "#27ae60" if is_connected else "#e74c3c"
db_path_display = os.path.dirname(DB_FILE)
if not db_path_display:
    db_path_display = "Local"

status_text = f"{status_msg} | Database: {db_path_display}"
status_label = tk.Label(status_frame, text=status_text, bg="#e8eaed", fg=status_color, font=('Segoe UI', 9), justify=tk.LEFT)
status_label.pack(side=tk.LEFT, padx=10, pady=5)

def update_status():
    is_connected, status_msg = check_database_connection()
    status_color = "#27ae60" if is_connected else "#e74c3c"
    status_text = f"{status_msg} | Database: {os.path.dirname(DB_FILE)}"
    status_label.config(text=status_text, fg=status_color)
    root.after(30000, update_status)

root.after(30000, update_status)

# Set up window close handler for database backup
root.protocol("WM_DELETE_WINDOW", on_closing)

# Cleanup old backups on startup
cleanup_old_backups()

root.mainloop()
