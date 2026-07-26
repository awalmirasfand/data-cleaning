"""
Data Cleaning Desktop App
=========================

A GUI tool for cleaning URL / domain data, deduplicating rows, and
classifying TLDs against accepted / rejected lists.

Cleaning logic mirrors the user-supplied Python script exactly:
    1. Clean Data    -> strip protocols, www, slashes, spaces, lowercase,
                        normalize via tldextract (domain.suffix)
    2. Dedup         -> drop_duplicates on Column A, keep first
    3. TLD Check     -> classify each domain's suffix against
                        accepted / rejected TLD lists; unknown TLDs
                        are reviewed in a bulk window and persisted

Usage:
    python main.py

TLD lists persist to ~/.data_cleaning_app/tld_config.json
"""

import os
import re
import json
from io import StringIO
from pathlib import Path

import pandas as pd
import tldextract
import customtkinter as ctk
import tkinter.ttk as ttk
from tkinter import filedialog, messagebox


# ============================================================
# Configuration
# ============================================================

APP_DIR = Path.home() / ".data_cleaning_app"
CONFIG_FILE = APP_DIR / "tld_config.json"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ============================================================
# TLD Manager  (persistence of accepted / rejected TLDs)
# ============================================================

class TLDManager:
    """Manages accepted / rejected TLD lists with JSON file persistence."""

    def __init__(self):
        self.accepted = set()
        self.rejected = set()
        self._load()

    def _load(self):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.accepted = self._normalize_set(data.get("accepted", []))
                self.rejected = self._normalize_set(data.get("rejected", []))
            except Exception:
                self.accepted = set()
                self.rejected = set()

    @staticmethod
    def _normalize_set(items):
        out = set()
        for t in items:
            t = str(t).strip().lower().lstrip(".")
            if t:
                out.add(t)
        return out

    def save(self):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "accepted": sorted(self.accepted),
                    "rejected": sorted(self.rejected),
                },
                f,
                indent=2,
            )

    def classify(self, suffix):
        """Returns 'accepted', 'rejected', or 'new'."""
        suffix = str(suffix).strip().lower().lstrip(".")
        if suffix in self.rejected:
            return "rejected"
        if suffix in self.accepted:
            return "accepted"
        return "new"

    def add_accepted(self, tld):
        tld = str(tld).strip().lower().lstrip(".")
        if tld:
            self.accepted.add(tld)
            self.rejected.discard(tld)

    def add_rejected(self, tld):
        tld = str(tld).strip().lower().lstrip(".")
        if tld:
            self.rejected.add(tld)
            self.accepted.discard(tld)


# ============================================================
# Data Processor  (mirrors user's script 1:1)
# ============================================================

class DataProcessor:
    """Cleaning / dedup / TLD-check logic copied from user's script."""

    @staticmethod
    def normalize_domain(text):
        """Per-domain normalizer - identical to user's normalize_domain()."""
        if pd.isna(text):
            return ""
        text = str(text).strip().lower()
        text = re.sub(r"^https?://", "", text)
        text = re.sub(r"^www\.", "", text)
        text = text.split("/")[0]
        text = text.split(" ")[0]
        text = text.replace(" ", "")
        ext = tldextract.extract(text)
        if ext.domain and ext.suffix:
            return f"{ext.domain}.{ext.suffix}"
        return text

    @staticmethod
    def clean_data(df):
        """
        STEP 1 - Clean Data  (matches user script exactly)
          * Ensure >= 11 columns
          * Clean Column A: fillna, strip, remove http(s):// and www.
          * Copy A -> K, strip slash / space / spaces, lowercase
          * Copy K -> A
          * Re-normalize via tldextract
        """
        df = df.copy()

        # Ensure at least 11 columns (Column K)
        while len(df.columns) < 11:
            df[f"Extra_{len(df.columns)+1}"] = ""

        # Initial cleaning of Column A
        df.iloc[:, 0] = (
            df.iloc[:, 0]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.replace(r"^https?://", "", regex=True)
            .str.replace(r"^www\.", "", regex=True)
        )

        # Copy A -> K (column index 10)
        df.iloc[:, 10] = df.iloc[:, 0]

        # Keep everything before first "/"
        df.iloc[:, 10] = df.iloc[:, 10].str.split("/", n=1).str[0]
        # Keep everything before first space
        df.iloc[:, 10] = df.iloc[:, 10].str.split(" ", n=1).str[0]
        # Remove remaining spaces
        df.iloc[:, 10] = df.iloc[:, 10].str.replace(" ", "", regex=False)
        # Lowercase
        df.iloc[:, 10] = df.iloc[:, 10].str.lower()
        # Copy K -> A
        df.iloc[:, 0] = df.iloc[:, 10]

        # Normalize domains using tldextract
        df.iloc[:, 0] = df.iloc[:, 0].apply(DataProcessor.normalize_domain)
        return df

    @staticmethod
    def remove_duplicates(df):
        """STEP 2 - Remove Duplicates (keep first occurrence on Column A)."""
        df = df.copy()
        return df.drop_duplicates(
            subset=df.columns[0], keep="first"
        ).reset_index(drop=True)

    @staticmethod
    def check_tlds(df, tld_manager):
        """
        STEP 3 - TLD Check.
        Returns: (df_with_column_D_set, new_tlds_found_set, counts_dict)
        """
        df = df.copy()

        # Ensure Column D exists
        while len(df.columns) < 4:
            df[f"Extra_{len(df.columns)+1}"] = ""

        new_tlds_found = set()
        counts = {"accepted": 0, "rejected": 0, "new tld": 0, "empty": 0}

        def check_tld(domain):
            if pd.isna(domain) or str(domain).strip() == "":
                counts["empty"] += 1
                return ""
            domain = str(domain).strip().lower()
            ext = tldextract.extract(domain)
            suffix = ext.suffix.lower()
            if not suffix:
                counts["empty"] += 1
                return ""

            cls = tld_manager.classify(suffix)
            if cls == "rejected":
                counts["rejected"] += 1
                return "rejected"
            if cls == "accepted":
                counts["accepted"] += 1
                return "accepted"
            # unknown
            new_tlds_found.add(suffix)
            counts["new tld"] += 1
            return "new tld"

        df.iloc[:, 3] = df.iloc[:, 0].apply(check_tld)
        return df, new_tlds_found, counts


# ============================================================
# TLD Manager Window  (view / edit accepted & rejected lists)
# ============================================================

class TLDManagerWindow(ctk.CTkToplevel):
    """Window for viewing / editing the accepted & rejected TLD lists."""

    def __init__(self, parent, tld_manager, on_save_callback):
        super().__init__(parent)
        self.title("Manage TLDs")
        self.geometry("820x600")
        self.tld_manager = tld_manager
        self.on_save_callback = on_save_callback

        self.transient(parent)
        self.grab_set()

        ctk.CTkLabel(
            self,
            text="Manage TLD Lists",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(pady=(20, 10))

        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=20, pady=10)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_columnconfigure(1, weight=1)
        main_frame.grid_rowconfigure(1, weight=1)

        self.text_boxes = {}
        self._build_column(main_frame, "Accepted TLDs", "accepted", 0)
        self._build_column(main_frame, "Rejected TLDs", "rejected", 1)

        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(fill="x", padx=20, pady=10)
        ctk.CTkButton(
            btn_frame, text="Save & Close", width=140, command=self._save
        ).pack(side="right", padx=5)
        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=100,
            fg_color="gray",
            command=self.destroy,
        ).pack(side="right", padx=5)

    def _build_column(self, parent, title, key, col):
        ctk.CTkLabel(
            parent,
            text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=col, pady=(10, 0), sticky="w", padx=20)

        text_box = ctk.CTkTextbox(parent, width=350, height=420)
        text_box.grid(row=1, column=col, sticky="nsew", padx=20, pady=10)
        tlds = sorted(getattr(self.tld_manager, key))
        text_box.insert("1.0", "\n".join(tlds))
        self.text_boxes[key] = text_box

        ctk.CTkLabel(
            parent,
            text="One TLD per line (e.g. com, org, net, co.uk)",
            font=ctk.CTkFont(size=11),
        ).grid(row=2, column=col, pady=(0, 10), sticky="w", padx=20)

    def _save(self):
        for key, tb in self.text_boxes.items():
            content = tb.get("1.0", "end").strip()
            new_set = set()
            if content:
                for line in content.split("\n"):
                    tld = line.strip().lower().lstrip(".")
                    if tld:
                        new_set.add(tld)
            setattr(self.tld_manager, key, new_set)

        self.tld_manager.save()
        self.on_save_callback()
        self.destroy()


# ============================================================
# New TLD Bulk Review Window
# ============================================================

class NewTLDReviewWindow(ctk.CTkToplevel):
    """Bulk-review window: user marks each new TLD as Accepted or Rejected."""

    def __init__(self, parent, new_tlds, on_apply_callback):
        super().__init__(parent)
        self.title("Review New TLDs")
        self.geometry("620x620")
        self.new_tlds = sorted(new_tlds)
        self.on_apply_callback = on_apply_callback
        self.choices = {}  # tld -> ctk.StringVar

        self.transient(parent)
        self.grab_set()

        ctk.CTkLabel(
            self,
            text=f"Review {len(self.new_tlds)} New TLD(s)",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(pady=(20, 5))
        ctk.CTkLabel(
            self,
            text="Mark each TLD as Accepted or Rejected, then click Apply.",
            font=ctk.CTkFont(size=12),
        ).pack(pady=(0, 10))

        bulk = ctk.CTkFrame(self)
        bulk.pack(fill="x", padx=20, pady=5)
        ctk.CTkButton(
            bulk,
            text="Accept All",
            width=120,
            command=lambda: self._set_all("Accepted"),
        ).pack(side="left", padx=5, pady=5)
        ctk.CTkButton(
            bulk,
            text="Reject All",
            width=120,
            fg_color="#dc2626",
            command=lambda: self._set_all("Rejected"),
        ).pack(side="left", padx=5, pady=5)

        scroll = ctk.CTkScrollableFrame(self)
        scroll.pack(fill="both", expand=True, padx=20, pady=10)

        for tld in self.new_tlds:
            row = ctk.CTkFrame(scroll)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(
                row, text=f".{tld}", width=180, anchor="w",
                font=ctk.CTkFont(size=13),
            ).pack(side="left", padx=10)
            var = ctk.StringVar(value="Accepted")  # default Accepted
            self.choices[tld] = var
            seg = ctk.CTkSegmentedButton(
                row, values=["Accepted", "Rejected"], variable=var
            )
            seg.pack(side="right", padx=10, pady=5)

        ctk.CTkButton(
            self,
            text=f"Apply Choices ({len(self.new_tlds)} TLDs)",
            height=40,
            command=self._apply,
        ).pack(pady=10)

    def _set_all(self, value):
        for var in self.choices.values():
            var.set(value)

    def _apply(self):
        result = {}
        for tld, var in self.choices.items():
            result[tld] = "accepted" if var.get() == "Accepted" else "rejected"
        self.on_apply_callback(result)
        self.destroy()


# ============================================================
# Main Application Window
# ============================================================

class DataCleaningApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Data Cleaning App")
        self.geometry("1320x880")
        self.minsize(1000, 700)

        # --- State ---
        self.original_df = None      # raw loaded data
        self.current_df = None       # current working state
        self.tld_manager = TLDManager()
        self.last_operation = None   # 'clean' | 'dedupe' | 'tld' | None
        self.workflow_mode = ctk.StringVar(value="Chain")
        self.theme_mode = ctk.StringVar(value="dark")
        self._pending_tld_df = None  # snapshot used for re-check after bulk review

        self._build_ui()
        self._update_status(
            "Ready. Paste data or browse a file, then click 'Load Input Data'."
        )
        self._update_tld_status()

    # ------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------

    def _build_ui(self):
        self._build_top_bar()

        content = ctk.CTkFrame(self)
        content.pack(fill="both", expand=True, padx=15, pady=5)
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(2, weight=1)

        self._build_input_section(content)
        self._build_action_buttons(content)
        self._build_table_preview(content)
        self._build_status_bar()

    def _build_top_bar(self):
        top = ctk.CTkFrame(self, height=50)
        top.pack(fill="x", padx=15, pady=(10, 5))

        ctk.CTkLabel(
            top,
            text="Data Cleaning App",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(side="left", padx=15)

        mode_frame = ctk.CTkFrame(top)
        mode_frame.pack(side="left", padx=20)
        ctk.CTkLabel(mode_frame, text="Mode:").pack(side="left", padx=5)
        ctk.CTkSegmentedButton(
            mode_frame,
            values=["Chain", "Restart from Input"],
            variable=self.workflow_mode,
        ).pack(side="left", padx=5)

        self.tld_status_label = ctk.CTkLabel(
            top, text="", font=ctk.CTkFont(size=11)
        )
        self.tld_status_label.pack(side="right", padx=15)

        ctk.CTkButton(
            top,
            text="Toggle Theme",
            width=120,
            command=self._toggle_theme,
        ).pack(side="right", padx=5)

    def _build_input_section(self, parent):
        frame = ctk.CTkFrame(parent)
        frame.grid(row=0, column=0, sticky="ew", padx=10, pady=5)

        ctk.CTkLabel(
            frame,
            text="Input Data",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=10, pady=(5, 0))
        ctk.CTkLabel(
            frame,
            text=(
                "Paste Excel columns (tab-separated, Column A = website URL), "
                "or load a .xlsx / .csv file."
            ),
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=10)

        self.input_text = ctk.CTkTextbox(frame, height=120)
        self.input_text.pack(fill="x", padx=10, pady=5)

        btn_row = ctk.CTkFrame(frame)
        btn_row.pack(fill="x", padx=10, pady=5)

        ctk.CTkButton(
            btn_row, text="Load Input Data", width=150,
            command=self._load_input,
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_row, text="Browse Excel / CSV...", width=170,
            command=self._browse_file,
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_row, text="Clear", width=80, fg_color="gray",
            command=self._clear_input,
        ).pack(side="left", padx=5)

        self.header_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            btn_row, text="First row is header",
            variable=self.header_var,
        ).pack(side="left", padx=20)

    def _build_action_buttons(self, parent):
        frame = ctk.CTkFrame(parent)
        frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)

        ctk.CTkLabel(
            frame,
            text="Operations",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=10, pady=(5, 0))

        btn_row = ctk.CTkFrame(frame)
        btn_row.pack(fill="x", padx=10, pady=5)

        ctk.CTkButton(
            btn_row, text="1. Clean Data", width=140,
            command=self._clean_data,
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_row, text="2. Remove Duplicates", width=170,
            command=self._remove_duplicates,
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_row, text="3. Check TLDs", width=140,
            command=self._check_tlds,
        ).pack(side="left", padx=5)

        ctk.CTkLabel(btn_row, text="|").pack(side="left", padx=10)

        ctk.CTkButton(
            btn_row, text="Manage TLDs", width=130, fg_color="#7c3aed",
            command=self._manage_tlds,
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_row, text="Download Excel", width=140, fg_color="#16a34a",
            command=self._download,
        ).pack(side="left", padx=5)

    def _build_table_preview(self, parent):
        frame = ctk.CTkFrame(parent)
        frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)

        ctk.CTkLabel(
            frame,
            text="Data Preview (first 100 rows)",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=10, pady=(5, 0))

        tree_frame = ctk.CTkFrame(frame)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.tree = ttk.Treeview(
            tree_frame, show="headings", selectmode="browse"
        )
        vsb = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.tree.yview
        )
        hsb = ttk.Scrollbar(
            tree_frame, orient="horizontal", command=self.tree.xview
        )
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")

        self._apply_tree_style()

    def _build_status_bar(self):
        self.status_bar = ctk.CTkFrame(self, height=40)
        self.status_bar.pack(fill="x", padx=15, pady=(0, 10))
        self.status_label = ctk.CTkLabel(self.status_bar, text="", anchor="w")
        self.status_label.pack(side="left", padx=10, pady=5, fill="x", expand=True)
        self.row_count_label = ctk.CTkLabel(
            self.status_bar, text="0 rows", anchor="e"
        )
        self.row_count_label.pack(side="right", padx=10, pady=5)

    def _apply_tree_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        if self.theme_mode.get() == "dark":
            style.configure(
                "Treeview",
                background="#2b2b3c",
                foreground="#e0e0e0",
                fieldbackground="#2b2b3c",
                bordercolor="#3b3b4f",
                rowheight=25,
            )
            style.configure(
                "Treeview.Heading",
                background="#1e1e2e",
                foreground="#e0e0e0",
                relief="flat",
            )
            style.map("Treeview", background=[("selected", "#3b82f6")])
            style.map(
                "Treeview.Heading",
                background=[("active", "#3b3b4f")],
            )
        else:
            style.configure(
                "Treeview",
                background="#ffffff",
                foreground="#1f2937",
                fieldbackground="#ffffff",
                bordercolor="#e5e7eb",
                rowheight=25,
            )
            style.configure(
                "Treeview.Heading",
                background="#f3f4f6",
                foreground="#1f2937",
                relief="flat",
            )
            style.map("Treeview", background=[("selected", "#bfdbfe")])
            style.map(
                "Treeview.Heading",
                background=[("active", "#e5e7eb")],
            )

    # ------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------

    def _toggle_theme(self):
        new = "light" if self.theme_mode.get() == "dark" else "dark"
        self.theme_mode.set(new)
        ctk.set_appearance_mode(new)
        self._apply_tree_style()

    # ------------------------------------------------------------
    # Input loading
    # ------------------------------------------------------------

    def _load_input(self):
        text = self.input_text.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning(
                "No Input", "Please paste data first or browse for a file."
            )
            return
        try:
            header = 0 if self.header_var.get() else None
            df = pd.read_csv(StringIO(text), sep="\t", header=header)
            # If only 1 column came back, try comma-separated
            if df.shape[1] == 1:
                try:
                    df2 = pd.read_csv(StringIO(text), header=header)
                    if df2.shape[1] > 1:
                        df = df2
                except Exception:
                    pass

            self.original_df = df
            self.current_df = df.copy()
            self.last_operation = None
            self._refresh_table(df)
            self._update_status(
                f"Loaded {len(df)} rows × {df.shape[1]} columns from pasted input."
            )
        except Exception as e:
            messagebox.showerror(
                "Parse Error", f"Failed to parse pasted data:\n{e}"
            )

    def _browse_file(self):
        path = filedialog.askopenfilename(
            title="Select Excel or CSV file",
            filetypes=[
                ("Excel files", "*.xlsx *.xls"),
                ("CSV files", "*.csv"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        try:
            if path.lower().endswith(".csv"):
                df = pd.read_csv(path)
            else:
                df = pd.read_excel(path, sheet_name=0)
            self.original_df = df
            self.current_df = df.copy()
            self.last_operation = None
            self._refresh_table(df)
            self._update_status(
                f"Loaded {len(df)} rows × {df.shape[1]} columns "
                f"from {os.path.basename(path)}."
            )
        except Exception as e:
            messagebox.showerror("File Error", f"Failed to load file:\n{e}")

    def _clear_input(self):
        self.input_text.delete("1.0", "end")
        self.original_df = None
        self.current_df = None
        self.last_operation = None
        self._refresh_table(None)
        self._update_status("Input cleared.")

    # ------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------

    def _get_working_df(self):
        """Return df to operate on, based on the current workflow mode."""
        if self.workflow_mode.get() == "Restart from Input":
            if self.original_df is None:
                messagebox.showwarning(
                    "No Data", "Please load input data first."
                )
                return None
            return self.original_df.copy()
        # chain
        if self.current_df is None:
            messagebox.showwarning("No Data", "Please load input data first.")
            return None
        return self.current_df.copy()

    def _clean_data(self):
        df = self._get_working_df()
        if df is None:
            return
        try:
            self.current_df = DataProcessor.clean_data(df)
            self.last_operation = "clean"
            self._refresh_table(self.current_df)
            self._update_status(
                f"✓ Cleaned data → {len(self.current_df)} rows. "
                f"Mode: {self.workflow_mode.get()}."
            )
        except Exception as e:
            messagebox.showerror("Clean Error", str(e))

    def _remove_duplicates(self):
        df = self._get_working_df()
        if df is None:
            return
        try:
            before = len(df)
            self.current_df = DataProcessor.remove_duplicates(df)
            self.last_operation = "dedupe"
            self._refresh_table(self.current_df)
            removed = before - len(self.current_df)
            self._update_status(
                f"✓ Removed {removed} duplicate(s) → "
                f"{len(self.current_df)} rows remain. "
                f"Mode: {self.workflow_mode.get()}."
            )
        except Exception as e:
            messagebox.showerror("Dedup Error", str(e))

    def _check_tlds(self):
        df = self._get_working_df()
        if df is None:
            return
        try:
            df, new_tlds, counts = DataProcessor.check_tlds(
                df, self.tld_manager
            )
            # Snapshot the pre-classification df so we can re-run after
            # the bulk review assigns each new TLD to accepted / rejected.
            # We strip Column D first because check_tlds overwrites it.
            pre_df = df.copy()
            if len(pre_df.columns) >= 4:
                pre_df.iloc[:, 3] = ""

            if new_tlds:
                # Show intermediate state (with "new tld" labels)
                self.current_df = df
                self.last_operation = "tld"
                self._refresh_table(df)
                self._update_status(
                    f"Found {len(new_tlds)} new TLD(s). "
                    f"Review window opened — please classify each. "
                    f"Currently: {counts['accepted']} accepted, "
                    f"{counts['rejected']} rejected."
                )

                def on_apply(choices):
                    for tld, choice in choices.items():
                        if choice == "accepted":
                            self.tld_manager.add_accepted(tld)
                        else:
                            self.tld_manager.add_rejected(tld)
                    self.tld_manager.save()
                    self._update_tld_status()

                    # Re-run check on the snapshot (now all TLDs are known)
                    df2, _, counts2 = DataProcessor.check_tlds(
                        pre_df, self.tld_manager
                    )
                    self.current_df = df2
                    self.last_operation = "tld"
                    self._refresh_table(df2)
                    self._update_status(
                        f"✓ TLD check complete. "
                        f"Accepted: {counts2['accepted']}, "
                        f"Rejected: {counts2['rejected']}. "
                        f"{len(new_tlds)} new TLD(s) classified and saved."
                    )

                NewTLDReviewWindow(self, new_tlds, on_apply)
            else:
                self.current_df = df
                self.last_operation = "tld"
                self._refresh_table(df)
                self._update_status(
                    f"✓ TLD check complete. "
                    f"Accepted: {counts['accepted']}, "
                    f"Rejected: {counts['rejected']}. "
                    f"No new TLDs found."
                )
        except Exception as e:
            messagebox.showerror("TLD Check Error", str(e))

    def _manage_tlds(self):
        def on_save():
            self._update_tld_status()
            self._update_status(
                f"TLD lists updated. "
                f"Accepted: {len(self.tld_manager.accepted)}, "
                f"Rejected: {len(self.tld_manager.rejected)}."
            )

        TLDManagerWindow(self, self.tld_manager, on_save)

    def _download(self):
        if self.current_df is None:
            messagebox.showwarning(
                "No Data", "No data to download. Perform an operation first."
            )
            return

        path = filedialog.asksaveasfilename(
            title="Save Excel file",
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
            initialfile="cleaned_data.xlsx",
        )
        if not path:
            return

        try:
            if self.last_operation == "tld":
                df = self.current_df.copy()
                while len(df.columns) < 4:
                    df[f"Extra_{len(df.columns)+1}"] = ""

                accepted_df = df[df.iloc[:, 3] == "accepted"].reset_index(
                    drop=True
                )
                rejected_df = df[df.iloc[:, 3] == "rejected"].reset_index(
                    drop=True
                )

                # Build TLD config sheet (col A = accepted, col B = rejected)
                acc_list = sorted(self.tld_manager.accepted)
                rej_list = sorted(self.tld_manager.rejected)
                max_len = max(len(acc_list), len(rej_list), 1)
                acc_padded = acc_list + [""] * (max_len - len(acc_list))
                rej_padded = rej_list + [""] * (max_len - len(rej_list))
                config_df = pd.DataFrame(
                    {
                        "Accepted TLDs": acc_padded,
                        "Rejected TLDs": rej_padded,
                    }
                )

                with pd.ExcelWriter(path, engine="openpyxl") as writer:
                    accepted_df.to_excel(
                        writer, sheet_name="Accepted", index=False
                    )
                    rejected_df.to_excel(
                        writer, sheet_name="Rejected", index=False
                    )
                    config_df.to_excel(
                        writer, sheet_name="TLD Config", index=False
                    )

                self._update_status(
                    f"✓ Downloaded to {os.path.basename(path)} "
                    f"(Accepted: {len(accepted_df)}, "
                    f"Rejected: {len(rejected_df)}, "
                    f"+ TLD Config sheet)."
                )
            else:
                sheet_name = (
                    "Sheet1"
                    if self.last_operation == "clean"
                    else "Cleaned"
                    if self.last_operation == "dedupe"
                    else "Data"
                )
                self.current_df.to_excel(
                    path, sheet_name=sheet_name, index=False, engine="openpyxl"
                )
                self._update_status(
                    f"✓ Downloaded {len(self.current_df)} rows "
                    f"to {os.path.basename(path)} (sheet: {sheet_name})."
                )
        except Exception as e:
            messagebox.showerror("Download Error", str(e))

    # ------------------------------------------------------------
    # Table & status updates
    # ------------------------------------------------------------

    def _refresh_table(self, df):
        self.tree.delete(*self.tree.get_children())

        if df is None or len(df) == 0:
            self.tree["columns"] = []
            self.row_count_label.configure(text="0 rows")
            return

        preview_df = df.head(100)
        cols = list(df.columns)
        self.tree["columns"] = [str(c) for c in cols]
        for col in cols:
            self.tree.heading(str(col), text=str(col))
            self.tree.column(str(col), width=140, anchor="w", stretch=True)

        for _, row in preview_df.iterrows():
            values = ["" if pd.isna(v) else str(v) for v in row.values]
            self.tree.insert("", "end", values=values)

        total = len(df)
        shown = len(preview_df)
        self.row_count_label.configure(
            text=f"{total} rows (showing {shown})"
        )

    def _update_status(self, message):
        self.status_label.configure(text=message)

    def _update_tld_status(self):
        self.tld_status_label.configure(
            text=(
                f"Accepted TLDs: {len(self.tld_manager.accepted)} | "
                f"Rejected TLDs: {len(self.tld_manager.rejected)}"
            )
        )


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    app = DataCleaningApp()
    app.mainloop()
