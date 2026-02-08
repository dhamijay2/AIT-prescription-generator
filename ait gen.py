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

def load_config():
    """Load config from Documents folder. Returns dict with defaults if not found."""
    config_path = get_config_path()
    if not config_path:
        return {
            "database_path": os.path.join(WORKING_DIR, "UC_Allergy_AIT.db"),
            "last_save_directory": WORKING_DIR,
            "allergen_overrides": {}
        }
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                # Validate paths exist; return defaults if not
                if not os.path.exists(config.get("database_path", "")):
                    config["database_path"] = os.path.join(WORKING_DIR, "UC_Allergy_AIT.db")
                if not os.path.exists(config.get("last_save_directory", "")):
                    config["last_save_directory"] = WORKING_DIR
                if not isinstance(config.get("allergen_overrides"), dict):
                    config["allergen_overrides"] = {}
                return config
        except Exception as e:
            print(f"Warning: Could not load config: {e}")
            return {
                "database_path": os.path.join(WORKING_DIR, "UC_Allergy_AIT.db"),
                "last_save_directory": WORKING_DIR,
                "allergen_overrides": {}
            }
    else:
        # First launch - return defaults
        return {
            "database_path": os.path.join(WORKING_DIR, "UC_Allergy_AIT.db"),
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
        
        # Ask user if they want to select existing database or create new one
        result = messagebox.askyesno(
            "Database Setup",
            "Would you like to select an existing database?\n\nYes: Select existing database\nNo: Create new database"
        )
        
        if result:  # User wants to select existing
            db_file = filedialog.askopenfilename(
                title="Select Database File",
                filetypes=[("Database files", "*.db"), ("All files", "*.*")],
                initialdir=os.path.expanduser("~")
            )
            if db_file:
                DB_FILE = db_file
                CURRENT_CONFIG['database_path'] = db_file
                save_config(CURRENT_CONFIG)
        else:  # User wants to create new
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
    {"name": "Kochia (Firebush)", "group": "Weed", "min_volume": 0.5, "max_volume": 1.0, "incompatible_groups": ["Mold", "Amer. Cockroach", "Ger. Cockroach"]},
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
        
        conn.commit()
        conn.close()
    except Exception as e:
        messagebox.showerror("Database Error", f"Failed to initialize database: {e}")


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

    def add_allergen(self, allergen_name, volume):
        """Adds an allergen to the vial if compatible and within volume limits."""
        allergen_data = next((a for a in ALLERGENS if a["name"] == allergen_name), None)
        if not allergen_data:
            return False

        if not self.is_compatible(allergen_data):
            return False

        if self.current_volume + volume > 5.0:
            return False

        if not (allergen_data["min_volume"] <= volume <= allergen_data["max_volume"]):
            return False

        self.allergens[allergen_name] = volume
        self.current_volume += volume
        return True

    def remaining_volume(self):
        """Calculates the remaining volume in the vial."""
        return 5.0 - self.current_volume

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
    
    # Database Path Section
    ttk.Label(settings_window, text="Database File:", font=('Segoe UI', 10, 'bold')).pack(padx=10, pady=(10, 5), anchor="w")
    
    db_frame = ttk.Frame(settings_window)
    db_frame.pack(fill=tk.X, padx=10, pady=5)
    
    db_path_var = tk.StringVar(value=CURRENT_CONFIG.get('database_path', DB_FILE))
    db_path_entry = ttk.Entry(db_frame, textvariable=db_path_var, width=50)
    db_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
    
    def browse_databases():
        """Browse for existing database or location for new one."""
        result = messagebox.askyesno("Database Selection", 
            "Do you want to:\n\nYes = Select existing database\nNo = Choose location for new database")
        
        if result:
            # Select existing database
            file_path = filedialog.askopenfilename(
                title="Select AIT Database",
                filetypes=[("SQLite Database", "*.db"), ("All Files", "*.*")],
                initialdir=os.path.dirname(CURRENT_CONFIG.get('database_path', DB_FILE))
            )
            if file_path:
                db_path_var.set(file_path)
        else:
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


def show_toast(message, duration=3000):
    """Displays a toast notification in the bottom-right corner of the window."""
    toast = tk.Toplevel(root)
    toast.wm_overrideredirect(True)
    toast.attributes('-topmost', True)
    
    # Style the toast
    toast.configure(bg='#333333')
    label = tk.Label(toast, text=message, bg='#333333', fg='white', 
                    font=('Segoe UI', 9), padx=15, pady=10)
    label.pack()
    
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
        prescription_json: Optional JSON string of the prescription (vials and volumes)
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Check if patient already exists by MRN
        cursor.execute('SELECT id FROM patients WHERE mrn = ?', (patient_data['mrn'],))
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
                    last_prescription_json = ?,
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
                prescription_json,
                patient_data['mrn']
            ))
        else:
            # Insert new patient
            cursor.execute('''
                INSERT INTO patients 
                (patient_name, dob, mrn, address, city, state, zip_code, phone, allergens, treatment_type, last_prescription_json)
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
                prescription_json
            ))
        
        conn.commit()
        conn.close()
        show_toast(f"Patient '{patient_data['patient_name']}' saved successfully.")
    
    except sqlite3.IntegrityError:
        messagebox.showerror("Error", f"Patient with MRN '{patient_data['mrn']}' already exists.")
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred while saving: {e}")

def load_patient():
    """Opens a new window to load an existing patient from the database."""

    def load_selected_patient():
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

            # Query database
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT patient_name, dob, mrn, address, city, state, zip_code, phone, allergens, treatment_type, last_prescription_json
                FROM patients
                WHERE patient_name = ? AND dob = ?
            ''', (name_part, dob_part))
            
            result = cursor.fetchone()
            conn.close()

            if result:
                patient_name, dob, mrn, address, city, state, zip_code, phone, allergens_str, treatment_type, prescription_json = result
                
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

                # Restore the previous prescription if available
                if prescription_json:
                    try:
                        prescription_data = json.loads(prescription_json)
                        vial_dicts = prescription_data.get('vials', [])
                        
                        # Restore vials from stored data
                        global last_vials, last_prescription_data, last_compounding_log_id
                        last_vials = []
                        for vial_dict in vial_dicts:
                            vial = Vial(vial_dict['label'])
                            for allergen_name, volume in vial_dict['allergens'].items():
                                vial.add_allergen(allergen_name, volume)
                            last_vials.append(vial)
                        
                        # Populate prescription data for displaying
                        last_prescription_data = {
                            'patient_name': patient_name,
                            'dob': dob,
                            'mrn': mrn,
                            'address': address,
                            'city': city,
                            'state': state,
                            'zip_code': zip_code,
                            'phone': phone,
                            'vial_type': prescription_data.get('vial_type', 'Environmental'),
                            'treatment_type': prescription_data.get('treatment_type', 'New Start'),
                            'prescriber_name': prescriber_var.get() if prescriber_var else ""
                        }
                        
                        # Get patient ID and recreate compounding log for current session
                        try:
                            conn = sqlite3.connect(DB_FILE)
                            cursor = conn.cursor()
                            cursor.execute("SELECT id FROM patients WHERE mrn = ?", (mrn,))
                            patient_result = cursor.fetchone()
                            patient_id = patient_result[0] if patient_result else None
                            conn.close()
                            
                            # Create a new compounding log to enable PDF exports
                            if patient_id and last_vials:
                                last_compounding_log_id = create_compounding_log(
                                    patient_id, 
                                    patient_name, 
                                    dob, 
                                    prescription_data.get('vial_type', 'Environmental'),
                                    prescription_data.get('treatment_type', 'New Start'),
                                    last_vials
                                )
                        except Exception as e:
                            print(f"Warning: Could not create compounding log: {e}")
                        
                        # Display the loaded prescription
                        display_prescription_output(last_vials, last_prescription_data, prescription_data.get('vial_type', 'Environmental'))
                        show_toast(f"Loaded prescription for {patient_name}")
                    except Exception as e:
                        print(f"Warning: Could not restore prescription: {e}")

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

        if not messagebox.askyesno("Confirm Delete", f"Delete patient '{selected_patient_str}'?"):
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
            load_window.destroy()
            load_patient()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to delete patient: {e}")

    # --- Create the Load Patient Window ---
    load_window = tk.Toplevel(root)
    load_window.title("Load Patient")

    patient_select_label = ttk.Label(load_window, text="Select Patient (Name DOB):")
    patient_select_label.pack(padx=10, pady=5)

    patient_select_var = tk.StringVar()
    patient_select_combo = ttk.Combobox(load_window, textvariable=patient_select_var)
    patient_select_combo.pack(padx=10, pady=5)

    # Populate the dropdown with existing patient names and DOBs from database
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT patient_name, dob FROM patients ORDER BY patient_name')
        rows = cursor.fetchall()
        conn.close()
        
        patient_strings = [f"{row[0]} {row[1]}" for row in rows]
        patient_select_combo['values'] = patient_strings

        if not patient_strings:
            messagebox.showinfo("No Patients", "No patient data found. Add patients first.")
            load_window.destroy()
            return

    except Exception as e:
        messagebox.showerror("Error", f"Error loading patient list: {e}")
        load_window.destroy()
        return

    # Buttons
    button_frame = ttk.Frame(load_window)
    button_frame.pack(pady=10)

    load_button = ttk.Button(button_frame, text="Load", command=load_selected_patient)
    load_button.pack(side=tk.LEFT, padx=5)

    delete_button = ttk.Button(button_frame, text="Delete", command=delete_selected_patient)
    delete_button.pack(side=tk.LEFT, padx=5)


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
    mode = vial_type_var.get()
    treatment_type = treatment_type_var.get()
    prescriber_name = prescriber_var.get() if prescriber_var else ""
    patient_name = patient_name_entry.get()
    mrn = mrn_entry.get()
    address = address_entry.get()
    city = city_entry.get()
    state = state_entry.get()
    zip_code = zip_entry.get()
    phone = phone_entry.get()

    if not patient_name or not mrn:
        messagebox.showerror("Error", "Please enter patient name and MRN.")
        return

    try:
        dob = dob_entry.get_date()
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
    
    # Generate vials with proper distribution
    max_vials = 4 if allow_fourth_vial_var and allow_fourth_vial_var.get() else 3
    vials = generate_vials(selected_allergens, max_vials=max_vials)
    
    if not vials:
        result_label.config(text="Error: Could not distribute allergens into vials.\nCheck allergen compatibility.")
        return

    # Serialize the prescription for storage
    prescription_json = serialize_vials_to_json(vials, mode, treatment_type)
    save_patient_data(patient_data, selected_allergens_str, prescription_json)
    
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
    
    # Store prescription data globally for PDF export
    global last_prescription_data, last_vials
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
    create_compounding_log(patient_id, patient_name, dob.strftime('%m-%d-%Y'), mode, treatment_type, vials)
    
    # Display the prescription
    display_prescription_output(last_vials, last_prescription_data, mode)


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
            prescription_text += f"  Total: 5.00 mL\n"
        
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
    edit_window.geometry("750x600")
    
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
    
    # Determine available vials for assignment
    max_allowed = 4 if (allow_fourth_vial_var and allow_fourth_vial_var.get()) else 3
    available_vials = [f"Vial {chr(65 + i)}" for i in range(max_allowed)]

    # Headers
    header_frame = ttk.Frame(scrollable_frame)
    header_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
    ttk.Label(header_frame, text="Allergen", font=("Segoe UI", 10, "bold"), width=30).pack(side=tk.LEFT)
    ttk.Label(header_frame, text="Vial Assignment", font=("Segoe UI", 10, "bold"), width=15).pack(side=tk.LEFT)
    ttk.Label(header_frame, text="Volume (mL)", font=("Segoe UI", 10, "bold"), width=15).pack(side=tk.LEFT)

    # Build edit controls for each vial
    for vial in last_vials:
        vial_frame = ttk.LabelFrame(scrollable_frame, text=f"{vial.label} (Current Total: {vial.current_volume:.2f} mL)")
        vial_frame.pack(fill=tk.X, padx=5, pady=5)
        
        for allergen_name in sorted(vial.allergens.keys()):
            # Ignore HSA Diluent for manual editing; it will be re-calculated on save
            if allergen_name == "HSA Diluent":
                continue
                
            current_volume = vial.allergens[allergen_name]
            
            row_frame = ttk.Frame(vial_frame)
            row_frame.pack(fill=tk.X, padx=5, pady=3)
            
            label = ttk.Label(row_frame, text=f"{allergen_name}:", width=30)
            label.pack(side=tk.LEFT, padx=5)
            
            # Vial Selector
            v_var = tk.StringVar(value=vial.label)
            v_combo = ttk.Combobox(row_frame, textvariable=v_var, values=available_vials, state="readonly", width=12)
            v_combo.pack(side=tk.LEFT, padx=5)

            # Volume Entry
            entry = ttk.Entry(row_frame, width=10)
            entry.pack(side=tk.LEFT, padx=5)
            entry.insert(0, f"{current_volume:.2f}")
            
            ml_label = ttk.Label(row_frame, text="mL")
            ml_label.pack(side=tk.LEFT)
            
            allergen_controls.append((allergen_name, v_var, entry))
    
    # Buttons
    button_frame = ttk.Frame(edit_window)
    button_frame.pack(fill=tk.X, padx=5, pady=10)
    
    def save_changes():
        """Validate and save vial and volume changes."""
        try:
            new_vial_assignments = {} # label -> {name: vol}
            
            # Collect and validate all entries
            for allergen_name, v_var, entry in allergen_controls:
                vial_label = v_var.get()
                try:
                    new_vol = float(entry.get())
                    if new_vol < 0.01:
                        messagebox.showerror("Error", f"{allergen_name}: minimum volume is 0.01 mL")
                        return
                    if new_vol > 5.0:
                        messagebox.showerror("Error", f"{allergen_name}: maximum volume is 5.0 mL")
                        return
                except ValueError:
                    messagebox.showerror("Error", f"Invalid volume for {allergen_name}")
                    return
                
                if vial_label not in new_vial_assignments:
                    new_vial_assignments[vial_label] = {}
                new_vial_assignments[vial_label][allergen_name] = new_vol
            
            # Check total volumes per vial
            for label, allergens in new_vial_assignments.items():
                total = sum(allergens.values())
                if total > 5.0:
                    messagebox.showerror("Error", f"{label}: total volume ({total:.2f} mL) exceeds 5.00 mL limit")
                    return
            
            # Create new Vial objects and enforce compatibility
            updated_vials = []
            allergen_map = {a["name"]: a for a in ALLERGENS}
            
            for label in sorted(new_vial_assignments.keys()):
                vial = Vial(label)
                for name, vol in new_vial_assignments[label].items():
                    # Skip adding diluent here, we'll add it after compatibility checks
                    if name == "HSA Diluent":
                        continue

                    allergen_data = allergen_map.get(name)
                    if allergen_data:
                        # Check compatibility
                        if not vial.is_compatible(allergen_data):
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
                
                # Automatically calculate and add HSA Diluent to reach 5.0 mL
                diluent_needed = 5.0 - vial.current_volume
                if diluent_needed > 0:
                    vial.allergens["HSA Diluent"] = round(diluent_needed, 2)
                    vial.current_volume = 5.0
                
                updated_vials.append(vial)
            
            last_vials = updated_vials
            
            # Update prescription display
            display_prescription_output(last_vials, last_prescription_data, last_prescription_data['vial_type'])
            
            # Re-serialize prescription for storage
            prescription_json = serialize_vials_to_json(last_vials, last_prescription_data['vial_type'], last_prescription_data['treatment_type'])
            
            # Get patient MRN for database update
            mrn = last_prescription_data.get('mrn')
            if prescription_json and mrn:
                try:
                    conn = sqlite3.connect(DB_FILE)
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE patients SET last_prescription_json = ? WHERE mrn = ?",
                        (prescription_json, mrn)
                    )
                    conn.commit()
                    
                    # Also update/re-create compounding log
                    cursor.execute("SELECT id FROM patients WHERE mrn = ?", (mrn,))
                    row = cursor.fetchone()
                    if row:
                        patient_id = row[0]
                        create_compounding_log(
                            patient_id, 
                            last_prescription_data['patient_name'], 
                            last_prescription_data['dob'],
                            last_prescription_data['vial_type'],
                            last_prescription_data['treatment_type'],
                            last_vials
                        )
                    conn.close()
                except Exception as e:
                    print(f"Warning: Could not update database: {e}")
            
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


def export_prescription_to_pdf():
    """Exports the current prescription to a PDF file with signature lines."""
    global last_save_directory
    if not last_prescription_data or not last_vials:
        messagebox.showwarning("Warning", "Please generate a prescription first before exporting.")
        return
    
    # Ask user where to save the file
    file_path = filedialog.asksaveasfilename(
        initialdir=last_save_directory,
        defaultextension=".pdf",
        filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")],
        initialfile=f"{last_prescription_data['patient_name'].replace(' ', '_')}_AIT_Prescription.pdf"
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
        
        dilution_text = ""
        for color, ratio in dilutions:
            dilution_text += f"{color} = {ratio}    "
        dilution_para = Paragraph(dilution_text, normal_style)
        story.append(dilution_para)
        story.append(Spacer(1, 0.06*inch))
        
        # Vial Composition Section - Compact
        composition_heading = Paragraph(f"VIAL COMPOSITION ({len(last_vials)} vial(s))", heading_style)
        story.append(composition_heading)
        story.append(Spacer(1, 0.04*inch))
        
        for vial in last_vials:
            # Vial header
            vial_header = Paragraph(f"<b>{vial.label}</b>", heading_style)
            story.append(vial_header)
            
            # Vial contents table
            vial_contents = []
            diluent_vol = vial.remaining_volume()
            for allergen, volume in vial.allergens.items():
                if allergen == "HSA Diluent":
                    diluent_vol += volume
                    continue
                vial_contents.append([allergen, f"{volume:.2f} mL"])
            vial_contents.append(["Diluent:", f"{diluent_vol:.2f} mL"])
            
            vial_table = Table(vial_contents, colWidths=[3.5*inch, 0.8*inch])
            vial_table.setStyle(TableStyle([
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8f4f8')),
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
            ]))
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
        messagebox.showinfo("Success", f"Prescription exported to:\n{file_path}")
    
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


def generate_label_data():
    """Generate label data for all vials with their dilutions.
    
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
    
    # Get current date and calculate lot number
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
        for allergen_name in vial.allergens.keys():
            allergen_data = next((a for a in ALLERGENS if a["name"] == allergen_name), None)
            if allergen_data:
                allergen_groups.add(allergen_data["group"])
        
        allergen_groups_str = ", ".join(sorted(allergen_groups))
        
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


def generate_labels_pdf(file_path):
    """Generate a PDF with labels in Avery 45160 format.
    
    Creates a multi-page PDF if needed, with all labels properly positioned
    on Avery 45160 label sheets.
    """
    try:
        label_data_list = generate_label_data()
        
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
        show_toast("Labels exported successfully")
        
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
        generate_labels_pdf(file_path)


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


def create_compounding_log(patient_id, patient_name, dob, vial_type, treatment_type, vials):
    """Create a compounding log record for the generated prescription.
    
    Returns the compounding log ID.
    """
    try:
        global last_compounding_log_id
        
        current_date = datetime.datetime.now().strftime("%m-%d-%Y")
        lot_number = calculate_lot_number(dob)
        
        conn = sqlite3.connect(DB_FILE)
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

        # Add items for each vial and allergen
        for vial in vials:
            for allergen_name, volume_used in vial.allergens.items():
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
        
        conn.commit()
        conn.close()
        
        last_compounding_log_id = compounding_log_id
        return compounding_log_id
    
    except Exception as e:
        messagebox.showerror("Error", f"Failed to create compounding log: {e}")
        return None


def export_compounding_log_pdf():
    """Export the compounding log to a PDF file."""
    global last_compounding_log_id
    
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
                
                # Calculate vial expiration date using helper function
                vial_expiration_str = calculate_vial_expiration(log['mix_date'], vial_items)
                
                vial_heading = Paragraph(f"<b>Vial {vial_letter}</b> (Mixed: {log['mix_date']} | Expires: {vial_expiration_str})", heading_style)
                story.append(vial_heading)
                
                vial_data = [['Allergen', 'Volume', 'Concentration', 'Manuf. Item #', 'Lot #', 'Expiration']]
                
                for item in vial_items:
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
            
            qc_text = "Final Yield per vial: 5 mL<br/>Quality Control Procedures: Color top confirmed; no particulates."
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
            show_toast("Compounding log exported successfully")
        
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
                    show_stock_management()
            
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save entry: {e}")
        
        save_btn = ttk.Button(button_frame, text="💾 Save", command=save_entry)
        save_btn.pack(side=tk.LEFT, padx=5)
        
        cancel_btn = ttk.Button(button_frame, text="Cancel", command=edit_window.destroy)
        cancel_btn.pack(side=tk.LEFT, padx=5)
    
    except Exception as e:
        messagebox.showerror("Error", f"Failed to open edit dialog: {e}")


def show_stock_management():
    """Open stock management window to view and edit stock extracts."""
    try:
        stock_window = tk.Toplevel(root)
        stock_window.title("Stock Inventory Management")
        stock_window.geometry("1200x600")
        
        def fetch_stocks(filter_allergen=None):
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if filter_allergen and filter_allergen != "All":
                cursor.execute('''
                    SELECT id, allergen_name, concentration, manufacturer_item, lot_number, 
                           expiration_date, vial_amount, is_active
                    FROM stock_extracts
                    WHERE allergen_name = ?
                    ORDER BY allergen_name, is_active DESC, expiration_date ASC
                ''', (filter_allergen,))
            else:
                cursor.execute('''
                    SELECT id, allergen_name, concentration, manufacturer_item, lot_number, 
                           expiration_date, vial_amount, is_active
                    FROM stock_extracts
                    ORDER BY allergen_name, is_active DESC, expiration_date ASC
                ''')
            stocks = cursor.fetchall()
            conn.close()
            return stocks

        def fetch_allergen_options():
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute('SELECT DISTINCT allergen_name FROM stock_extracts ORDER BY allergen_name')
            names = [row[0] for row in cursor.fetchall()]
            conn.close()
            return ["All"] + names
        
        # Filter controls
        filter_frame = ttk.Frame(stock_window)
        filter_frame.pack(fill=tk.X, padx=10, pady=(10, 0))

        ttk.Label(filter_frame, text="Filter by Allergen:").pack(side=tk.LEFT)
        allergen_filter_var = tk.StringVar(value="All")
        allergen_filter_combo = ttk.Combobox(filter_frame, textvariable=allergen_filter_var,
                             values=fetch_allergen_options(), state='readonly', width=30)
        allergen_filter_combo.pack(side=tk.LEFT, padx=6)

        # Create treeview
        frame = ttk.Frame(stock_window)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        columns = ("ID", "Allergen", "Concentration", "Manuf. Item", "Lot", "Expiration", "Vial Amt", "Active")
        tree = ttk.Treeview(frame, columns=columns, height=20, selectmode='extended')
        
        # Configure columns
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

        def populate_tree(filter_allergen=None):
            for row_id in tree.get_children():
                tree.delete(row_id)
            current_tag = 'allergen_light'
            last_allergen = None
            for stock in fetch_stocks(filter_allergen):
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
            stock_window.after(5000, refresh_expiring_highlights)

        def apply_filter(*args):
            populate_tree(allergen_filter_var.get())

        allergen_filter_combo.bind("<<ComboboxSelected>>", apply_filter)
        populate_tree()
        refresh_expiring_highlights()
        
        # Add buttons
        button_frame = ttk.Frame(stock_window)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        def add_entry():
            show_stock_edit_dialog(stock_id=None, parent_window=stock_window)
        
        def edit_entry():
            selected = tree.selection()
        def edit_entry(selected_item=None):
            if selected_item is None:
                selected = tree.selection()
                if not selected:
                    messagebox.showwarning("Warning", "Please select a stock item to edit.")
                    return
                selected_item = selected[0]

            values = tree.item(selected_item)['values']
            stock_id = values[0]
            show_stock_edit_dialog(stock_id=stock_id, parent_window=stock_window)

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

            if messagebox.askyesno("Confirm Delete", f"Delete {len(entries)} selected item(s)?"):
                try:
                    conn = sqlite3.connect(DB_FILE)
                    cursor = conn.cursor()
                    cursor.executemany("DELETE FROM stock_extracts WHERE id = ?", [(entry[0],) for entry in entries])
                    conn.commit()
                    conn.close()

                    show_toast(f"Deleted {len(entries)} item(s)")
                    stock_window.destroy()
                    show_stock_management()

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
                stock_window.destroy()
                show_stock_management()

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
        
        close_btn = ttk.Button(button_frame, text="Close", command=stock_window.destroy)
        close_btn.pack(side=tk.LEFT, padx=5)
    

    except Exception as e:
        messagebox.showerror("Error", f"Failed to open stock management: {e}")


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
    """Updates the visible allergen checkboxes based on vial type."""
    mode = vial_type_var.get()

    if mode == "Environmental":
        for widget in venom_allergen_frame.winfo_children():
            widget.grid_remove()
        for frame in environmental_allergen_frames:
            frame.grid()

    elif mode == "Venom":
        for frame in environmental_allergen_frames:
            frame.grid_remove()
        for i, allergen in enumerate(venom_allergens):
            venom_allergen_checkboxes[i].grid()

    else:
        for frame in environmental_allergen_frames:
            frame.grid_remove()
        for widget in venom_allergen_frame.winfo_children():
            widget.grid_remove()


def clear_fields():
    """Clears all input fields and checkbox selections."""
    patient_name_entry.delete(0, tk.END)
    dob_entry.set_date(datetime.date.today())
    mrn_entry.delete(0, tk.END)
    address_entry.delete(0, tk.END)
    city_entry.delete(0, tk.END)
    state_entry.delete(0, tk.END)
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
    result_label.config(text="")  # Clear result label


# --- Main Application Window ---
# Check for first launch and get database location if needed
handle_first_launch()

# Initialize database
init_database()

root = tk.Tk()
root.title("Allergen Immunotherapy Prescription Generator by Yashu Dhamija MD 2026 version 1.0")
root.geometry("1800x900")

# --- Create Menu Bar ---
menubar = tk.Menu(root)
root.config(menu=menubar)

file_menu = tk.Menu(menubar, tearoff=0)
menubar.add_cascade(label="File", menu=file_menu)
file_menu.add_command(label="Settings", command=open_settings)
file_menu.add_command(label="Dose Ranges", command=open_dose_ranges_window)
file_menu.add_separator()
file_menu.add_command(label="Exit", command=root.quit)

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

# Mousewheel scrolling for left canvas
left_canvas.bind("<Enter>", lambda e: left_canvas.bind_all("<MouseWheel>", _on_mousewheel_left))
left_canvas.bind("<Leave>", lambda e: left_canvas.unbind_all("<MouseWheel>"))

def _on_mousewheel_left(event):
    left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

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

# Mousewheel scrolling for right canvas
right_canvas.bind("<Enter>", lambda e: right_canvas.bind_all("<MouseWheel>", _on_mousewheel_right))
right_canvas.bind("<Leave>", lambda e: right_canvas.unbind_all("<MouseWheel>"))

def _on_mousewheel_right(event):
    right_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

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

# Phone Number
phone_label = ttk.Label(patient_info_frame, text="Phone Number:", style='Subheader.TLabel')
phone_label.grid(row=6, column=0, padx=6, pady=4, sticky="w")
phone_entry = ttk.Entry(patient_info_frame, width=40)
phone_entry.grid(row=6, column=1, padx=6, pady=4, sticky="ew")

# Zip Code
zip_label = ttk.Label(patient_info_frame, text="Zip Code:", style='Subheader.TLabel')
zip_label.grid(row=7, column=0, padx=6, pady=4, sticky="w")
zip_entry = ttk.Entry(patient_info_frame, width=40)
zip_entry.grid(row=7, column=1, padx=6, pady=4, sticky="ew")

patient_info_frame.columnconfigure(1, weight=1)

# --- Vial Type Selection ---
controls_frame = ttk.Frame(form_frame)
controls_frame.grid(row=8, column=0, padx=8, pady=6, sticky="ew")

vial_type_label = ttk.Label(controls_frame, text="Vial Type:", style='Subheader.TLabel')
vial_type_label.pack(side=tk.LEFT, padx=5)

vial_type_var = tk.StringVar(value="Environmental")
vial_type_var.trace_add("write", update_allergen_options)

vial_type_combo = ttk.Combobox(controls_frame, textvariable=vial_type_var,
                               values=["Environmental", "Venom"], state='readonly', width=20)
vial_type_combo.pack(side=tk.LEFT, padx=5)

# --- Treatment Type Selection and Load Patient Button ---
treatment_label = ttk.Label(controls_frame, text="Treatment Type:", style='Subheader.TLabel')
treatment_label.pack(side=tk.LEFT, padx=(15, 5))

treatment_type_var = tk.StringVar(value="New Start")
treatment_combo = ttk.Combobox(controls_frame, textvariable=treatment_type_var,
                               values=["New Start", "Maintenance"], state='readonly', width=20)
treatment_combo.pack(side=tk.LEFT, padx=5)

allow_fourth_vial_var = tk.BooleanVar(value=False)
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

# --- Environmental Allergen Checkboxes ---
environmental_allergen_frames = []
environmental_allergen_vars = {}

# --- Mold Group ---
mold_frame = ttk.LabelFrame(form_frame, text="🌱 Mold")
mold_frame.grid(row=10, column=0, padx=8, pady=6, sticky="ew")
environmental_allergen_frames.append(mold_frame)
mold_allergens = ["Aspergillus", "Alternaria", "Cladosporium", "Penicillium"]
for i, allergen in enumerate(mold_allergens):
    var = tk.BooleanVar()
    environmental_allergen_vars[allergen] = var
    checkbox = ttk.Checkbutton(mold_frame, text=allergen, variable=var)
    checkbox.grid(row=i // 2, column=i % 2, padx=6, pady=3, sticky="w")

# --- Tree Group ---
tree_frame = ttk.LabelFrame(form_frame, text="🌳 Tree")
tree_frame.grid(row=11, column=0, padx=8, pady=6, sticky="ew")
environmental_allergen_frames.append(tree_frame)
tree_allergens = ["Ash", "Birch (Oak)", "Cedar", "Elm", "Hackberry (Elm)", "Maple", "Sycamore", "Walnut (Pecan)",
                  "Willow (Cottonwood)", "Mulberry"]
for i, allergen in enumerate(tree_allergens):
    var = tk.BooleanVar()
    environmental_allergen_vars[allergen] = var
    checkbox = ttk.Checkbutton(tree_frame, text=allergen, variable=var)
    checkbox.grid(row=i // 2, column=i % 2, padx=6, pady=3, sticky="w")

# --- Grass Group ---
grass_frame = ttk.LabelFrame(form_frame, text="🌾 Grass")
grass_frame.grid(row=12, column=0, padx=8, pady=6, sticky="ew")
environmental_allergen_frames.append(grass_frame)
grass_allergens = ["Timothy", "Johnson", "Bermuda"]
for i, allergen in enumerate(grass_allergens):
    var = tk.BooleanVar()
    environmental_allergen_vars[allergen] = var
    checkbox = ttk.Checkbutton(grass_frame, text=allergen, variable=var)
    checkbox.grid(row=i // 2, column=i % 2, padx=6, pady=3, sticky="w")

# --- Weed Group ---
weed_frame = ttk.LabelFrame(form_frame, text="🌿 Weed")
weed_frame.grid(row=13, column=0, padx=8, pady=6, sticky="ew")
environmental_allergen_frames.append(weed_frame)
weed_allergens = ["Cocklebur", "Yellow Dock (Sheep Sorrel)", "Kochia (Firebush)", "Lamb's Quarter", "Mugwort",
                  "Pigweed", "English Plantain", "Russian Thistle", "Ragweed"]
for i, allergen in enumerate(weed_allergens):
    var = tk.BooleanVar()
    environmental_allergen_vars[allergen] = var
    checkbox = ttk.Checkbutton(weed_frame, text=allergen, variable=var)
    checkbox.grid(row=i // 2, column=i % 2, padx=6, pady=3, sticky="w")

# --- Other Group ---
other_frame = ttk.LabelFrame(form_frame, text="🐾 Other")
other_frame.grid(row=14, column=0, padx=8, pady=6, sticky="ew")
environmental_allergen_frames.append(other_frame)
other_allergens = ["Cat", "Dog - UF", "Dog - Epithelium", "Mouse", "Rat", "Horse", "Amer. Cockroach", "Ger. Cockroach",
                   "Dust Mite Mix"]
for i, allergen in enumerate(other_allergens):
    var = tk.BooleanVar()
    environmental_allergen_vars[allergen] = var
    checkbox = ttk.Checkbutton(other_frame, text=allergen, variable=var)
    checkbox.grid(row=i // 2, column=i % 2, padx=6, pady=3, sticky="w")

# Add trace callbacks for dog extract mutual exclusivity
environmental_allergen_vars["Dog - UF"].trace_add("write", enforce_dog_mutual_exclusivity)
environmental_allergen_vars["Dog - Epithelium"].trace_add("write", enforce_dog_mutual_exclusivity)

# --- Venom Allergen Checkboxes ---
venom_allergen_frame = ttk.LabelFrame(form_frame, text="🐝 Venom Allergens")
venom_allergen_frame.grid(row=15, column=0, columnspan=2, padx=8, pady=6, sticky="ew")

venom_allergens = ["Honey Bee", "Yellow Jacket", "Yellow Faced Hornet", "White Faced Hornet", "Wasp"]
venom_allergen_vars = {}
venom_allergen_checkboxes = []

for i, allergen in enumerate(venom_allergens):
    var = tk.BooleanVar()
    venom_allergen_vars[allergen] = var
    checkbox = ttk.Checkbutton(venom_allergen_frame, text=allergen, variable=var)
    checkbox.grid(row=i // 2, column=i % 2, padx=6, pady=3, sticky="w")
    venom_allergen_checkboxes.append(checkbox)

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

stock_mgmt_button = ttk.Button(button_frame1, text="🏷️ Stock Management", command=show_stock_management)
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
        conn = sqlite3.connect(DB_FILE)
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

    except Exception as e:
        print(f"Warning: Failed to refresh expiring extracts list: {e}")

    root.after(5000, refresh_expiring_extracts)

refresh_expiring_extracts()

output_frame.columnconfigure(0, weight=1)
output_frame.rowconfigure(0, weight=1)
output_frame.rowconfigure(1, weight=0)

root.mainloop()
