#!/usr/bin/env python3
"""
HTML Presentation to PDF Converter - Improved Edition
A production-ready application for converting HTML slides to a merged PDF.

Requirements:
    pip install playwright pypdf tkinterdnd2
    playwright install chromium
"""

import os
import sys
import json
import asyncio
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from threading import Thread

try:
    from playwright.async_api import async_playwright
    from pypdf import PdfWriter, PdfReader
    from tkinterdnd2 import TkinterDnD, DND_FILES
except ImportError as e:
    print(f"Missing required package: {e}")
    print("\nPlease install required packages:")
    print("pip install playwright pypdf tkinterdnd2")
    print("playwright install chromium")
    sys.exit(1)


class Settings:
    """Application settings manager."""
    
    def __init__(self):
        self.settings_file = Path.home() / '.html2pdf_settings.json'
        self.defaults = {
            'default_output_folder': str(Path.home() / 'Documents'),
            'auto_open_pdf': True,
            'pdf_quality': 'high',  # high, medium, low
            'window_width': 1200,
            'window_height': 800,
            'recent_files': [],
            'max_recent_files': 10
        }
        self.data = self.load()
        
    def load(self) -> dict:
        """Load settings from file."""
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r') as f:
                    loaded = json.load(f)
                    return {**self.defaults, **loaded}
            except Exception as e:
                print(f"Error loading settings: {e}")
        return self.defaults.copy()
        
    def save(self):
        """Save settings to file."""
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print(f"Error saving settings: {e}")
            
    def get(self, key: str, default=None):
        """Get a setting value."""
        return self.data.get(key, default or self.defaults.get(key))
        
    def set(self, key: str, value):
        """Set a setting value."""
        self.data[key] = value
        self.save()
        
    def add_recent_file(self, filepath: str):
        """Add a file to recent files list."""
        recent = self.get('recent_files', [])
        if filepath in recent:
            recent.remove(filepath)
        recent.insert(0, filepath)
        recent = recent[:self.get('max_recent_files')]
        self.set('recent_files', recent)


class Slide:
    """Represents a single HTML slide."""
    
    def __init__(self, slide_id: int, content: str, source: str = "pasted"):
        self.id = slide_id
        self.content = content
        self.source = source  # "file" or "pasted"
        self.filename = source if source != "pasted" else f"Slide {slide_id}"
        self.width = None
        self.height = None
        self.pdf_path = None
        
    def __repr__(self):
        return f"Slide({self.id}, {self.filename})"


class SlideCard(tk.Frame):
    """Custom widget for displaying a slide as a card."""
    
    def __init__(self, parent, slide: Slide, index: int, app, **kwargs):
        super().__init__(parent, **kwargs)
        self.slide = slide
        self.index = index
        self.app = app
        self.selected = False
        self.dragging = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        
        # Configure card appearance
        self.config(
            bg='white',
            relief='raised',
            borderwidth=2,
            highlightthickness=1,
            highlightbackground='#cccccc',
            cursor='hand2'
        )
        
        # Create card content
        self.create_widgets()
        
        # Bind events
        self.bind_events()
        
        # Context menu
        self.create_context_menu()
        
    def create_widgets(self):
        """Create card widgets."""
        # Padding frame
        content = tk.Frame(self, bg='white')
        content.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Icon
        self.icon_label = tk.Label(
            content,
            text="📄",
            font=('Segoe UI Emoji', 32),
            bg='white',
            fg='#2196F3'
        )
        self.icon_label.pack(pady=(5, 10))
        
        # Slide number badge
        self.number_label = tk.Label(
            content,
            text=f"#{self.index + 1}",
            font=('Helvetica', 11, 'bold'),
            bg='#2196F3',
            fg='white',
            padx=8,
            pady=2,
            relief='flat'
        )
        self.number_label.pack(pady=(0, 5))
        
        # Filename
        filename = self.slide.filename
        if len(filename) > 25:
            filename = filename[:22] + "..."
        
        self.name_label = tk.Label(
            content,
            text=filename,
            font=('Helvetica', 9),
            bg='white',
            fg='#333333',
            wraplength=150
        )
        self.name_label.pack(pady=(0, 5))
        
        # Dimensions
        self.dim_label = tk.Label(
            content,
            text=self.get_dimension_text(),
            font=('Helvetica', 8),
            bg='white',
            fg='#999999'
        )
        self.dim_label.pack()
        
    def get_dimension_text(self):
        """Get dimension text for display."""
        if self.slide.width and self.slide.height:
            return f"{self.slide.width} × {self.slide.height}px"
        return "Not processed"
        
    def bind_events(self):
        """Bind mouse events."""
        # Bind to frame and all children
        widgets = [self] + self.get_all_children()
        
        for widget in widgets:
            # Selection
            widget.bind('<Button-1>', self.on_mouse_down)
            widget.bind('<Double-Button-1>', self.on_double_click)
            
            # Drag and drop
            widget.bind('<B1-Motion>', self.on_drag)
            widget.bind('<ButtonRelease-1>', self.on_mouse_up)
            
            # Context menu
            widget.bind('<Button-3>', self.on_right_click)
            
            # Hover effects
            widget.bind('<Enter>', self.on_enter)
            widget.bind('<Leave>', self.on_leave)
    
    def get_all_children(self):
        """Get all child widgets recursively."""
        children = []
        for child in self.winfo_children():
            children.append(child)
            if hasattr(child, 'winfo_children'):
                children.extend(self.get_all_children_recursive(child))
        return children
    
    def get_all_children_recursive(self, widget):
        """Recursively get all children."""
        children = []
        for child in widget.winfo_children():
            children.append(child)
            if hasattr(child, 'winfo_children'):
                children.extend(self.get_all_children_recursive(child))
        return children
        
    def create_context_menu(self):
        """Create context menu."""
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="👁 Preview", command=self.preview)
        self.context_menu.add_command(label="⎘ Duplicate", command=self.duplicate)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="✗ Remove", command=self.remove)
        
    def on_mouse_down(self, event):
        """Handle mouse down - start selection or drag."""
        self.drag_start_x = event.x_root
        self.drag_start_y = event.y_root
        self.dragging = False
        
        # Handle selection
        ctrl_pressed = (event.state & 0x4) != 0
        self.app.select_slide(self.index, ctrl_pressed)
        
    def on_drag(self, event):
        """Handle dragging motion."""
        dx = event.x_root - self.drag_start_x
        dy = event.y_root - self.drag_start_y
        distance = (dx*dx + dy*dy) ** 0.5
        
        # Start drag if moved more than 10 pixels
        if distance > 10 and not self.dragging:
            self.dragging = True
            self.start_drag()
            
        if self.dragging:
            self.update_drag(event.x_root, event.y_root)
            
    def on_mouse_up(self, event):
        """Handle mouse up - end drag or click."""
        if self.dragging:
            self.end_drag(event.x_root, event.y_root)
            self.dragging = False
        
    def on_double_click(self, event):
        """Handle double click - preview."""
        self.app.preview_slide_at_index(self.index)
        
    def on_right_click(self, event):
        """Show context menu."""
        self.app.select_slide(self.index, False)
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()
            
    def on_enter(self, event):
        """Handle mouse enter - hover effect."""
        if not self.selected and not self.dragging:
            self.config(
                relief='raised',
                borderwidth=2,
                highlightbackground='#2196F3',
                highlightthickness=2
            )
            
    def on_leave(self, event):
        """Handle mouse leave - remove hover effect."""
        if not self.selected and not self.dragging:
            self.config(
                relief='raised',
                borderwidth=2,
                highlightbackground='#cccccc',
                highlightthickness=1
            )
            
    def start_drag(self):
        """Start dragging visual feedback."""
        self.config(
            relief='raised',
            borderwidth=3,
            bg='#E3F2FD'
        )
        self.lift()
        
    def update_drag(self, x, y):
        """Update drag position."""
        # Find target card under cursor
        target = self.find_card_at_position(x, y)
        if target and target != self:
            self.app.show_drop_indicator(target.index)
        else:
            self.app.hide_drop_indicator()
            
    def end_drag(self, x, y):
        """End dragging."""
        self.config(
            relief='raised',
            borderwidth=2,
            bg='white'
        )
        
        # Find target and perform move
        target = self.find_card_at_position(x, y)
        if target and target != self:
            self.app.move_slide(self.index, target.index)
        
        self.app.hide_drop_indicator()
        
    def find_card_at_position(self, x, y):
        """Find SlideCard at given position."""
        widget = self.winfo_containing(x, y)
        while widget:
            if isinstance(widget, SlideCard) and widget != self:
                return widget
            if widget == self.app.slides_container:
                break
            widget = widget.master
        return None
        
    def set_selected(self, selected: bool):
        """Set selection state."""
        self.selected = selected
        if selected:
            self.config(
                bg='#E3F2FD',
                relief='solid',
                borderwidth=3,
                highlightbackground='#1976D2',
                highlightthickness=2
            )
            # Update all child backgrounds
            self.update_child_bg('#E3F2FD')
        else:
            self.config(
                bg='white',
                relief='raised',
                borderwidth=2,
                highlightbackground='#cccccc',
                highlightthickness=1
            )
            # Update all child backgrounds
            self.update_child_bg('white')
            
    def update_child_bg(self, color):
        """Update background color of all children."""
        for child in self.get_all_children():
            try:
                if isinstance(child, (tk.Label, tk.Frame)):
                    if child != self.number_label:  # Keep number badge blue
                        child.config(bg=color)
            except:
                pass
                
    def update_index(self, new_index: int):
        """Update the displayed index."""
        self.index = new_index
        self.number_label.config(text=f"#{new_index + 1}")
        
    def update_dimensions(self):
        """Update dimensions display."""
        self.dim_label.config(text=self.get_dimension_text())
        
    def preview(self):
        """Preview this slide."""
        self.app.preview_slide_at_index(self.index)
        
    def duplicate(self):
        """Duplicate this slide."""
        self.app.duplicate_slide(self.index)
        
    def remove(self):
        """Remove this slide."""
        self.app.remove_slide_at_index(self.index)


class PDFConverterApp:
    """Main application class for HTML to PDF conversion."""
    
    def __init__(self, root):
        self.root = root
        self.root.title("HTML Presentation to PDF Converter")
        
        # Settings
        self.settings = Settings()
        
        # Apply saved window size
        width = self.settings.get('window_width')
        height = self.settings.get('window_height')
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(900, 600)
        
        # Application state
        self.slides: List[Slide] = []
        self.slide_counter = 0
        self.temp_dir = None
        self.output_pdf_path = None
        self.is_processing = False
        self.selected_indices = set()
        self.slide_cards = []
        self.drop_indicator = None
        
        # Styling
        self.setup_styles()
        
        # Build UI
        self.setup_ui()
        
        # Setup keyboard shortcuts
        self.setup_shortcuts()
        
        # Setup drag and drop
        self.setup_drag_drop()
        
        # Setup cleanup on close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Track window size changes
        self.root.bind('<Configure>', self.on_window_configure)
        
    def setup_styles(self):
        """Configure ttk styles for a modern look."""
        style = ttk.Style()
        
        # Try to use a modern theme
        available_themes = style.theme_names()
        if 'clam' in available_themes:
            style.theme_use('clam')
        elif 'vista' in available_themes:
            style.theme_use('vista')
            
        # Configure colors
        style.configure('Title.TLabel', font=('Helvetica', 16, 'bold'))
        style.configure('Subtitle.TLabel', font=('Helvetica', 10))
        style.configure('Action.TButton', padding=8)
        style.configure('Primary.TButton', padding=10, font=('Helvetica', 10, 'bold'))
        
    def setup_ui(self):
        """Build the user interface."""
        # Menu bar
        self.setup_menu()
        
        # Main container
        main_container = ttk.Frame(self.root, padding="10")
        main_container.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_container.columnconfigure(0, weight=1)
        main_container.rowconfigure(1, weight=1)
        
        # Header
        self.setup_header(main_container)
        
        # Content area (slides + log)
        content_frame = ttk.Frame(main_container)
        content_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(10, 0))
        content_frame.columnconfigure(0, weight=1)
        content_frame.rowconfigure(0, weight=1)
        
        # Paned window for slides and log
        paned = ttk.PanedWindow(content_frame, orient=tk.HORIZONTAL)
        paned.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Left: Slides panel
        slides_panel = self.setup_slides_panel(paned)
        paned.add(slides_panel, weight=2)
        
        # Right: Log panel
        log_panel = self.setup_log_panel(paned)
        paned.add(log_panel, weight=1)
        
        # Footer with actions
        self.setup_footer(main_container)
        
    def setup_menu(self):
        """Create menu bar."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Add Files... (Ctrl+O)", command=self.add_file_slides)
        file_menu.add_command(label="Paste HTML (Ctrl+V)", command=self.add_pasted_slide)
        file_menu.add_separator()
        
        # Recent files submenu
        self.recent_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Recent Files", menu=self.recent_menu)
        self.update_recent_files_menu()
        
        file_menu.add_separator()
        file_menu.add_command(label="Convert to PDF (Ctrl+S)", command=self.start_conversion)
        file_menu.add_separator()
        file_menu.add_command(label="Settings (Ctrl+,)", command=self.show_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_closing)
        
        # Edit menu
        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="Select All (Ctrl+A)", command=self.select_all_slides)
        edit_menu.add_command(label="Deselect All (Escape)", command=self.deselect_all_slides)
        edit_menu.add_separator()
        edit_menu.add_command(label="Duplicate Selected (Ctrl+D)", command=self.duplicate_selected)
        edit_menu.add_command(label="Remove Selected (Delete)", command=self.remove_selected_slides)
        edit_menu.add_command(label="Clear All Slides", command=self.clear_all_slides)
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Refresh Display (F5)", command=self.update_slides_display)
        view_menu.add_separator()
        view_menu.add_command(label="Clear Log", command=self.clear_log)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Keyboard Shortcuts", command=self.show_shortcuts)
        help_menu.add_command(label="About", command=self.show_about)
        
    def setup_header(self, parent):
        """Create header section."""
        header_frame = ttk.Frame(parent)
        header_frame.grid(row=0, column=0, sticky=(tk.W, tk.E))
        header_frame.columnconfigure(0, weight=1)
        
        title = ttk.Label(header_frame, text="📄 HTML Presentation to PDF Converter", 
                         style='Title.TLabel')
        title.grid(row=0, column=0, sticky=tk.W)
        
        subtitle = ttk.Label(header_frame, 
                           text="Drag & drop HTML files • Click to select • Drag to reorder • Convert to PDF",
                           style='Subtitle.TLabel', foreground='gray')
        subtitle.grid(row=1, column=0, sticky=tk.W, pady=(2, 0))
        
    def setup_slides_panel(self, parent):
        """Create the slides management panel."""
        panel = ttk.Frame(parent)
        
        # Toolbar
        toolbar = ttk.Frame(panel)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(toolbar, text="Slides:", font=('Helvetica', 11, 'bold')).pack(side=tk.LEFT)
        
        ttk.Button(toolbar, text="➕ Add", command=self.add_file_slides,
                  style='Action.TButton').pack(side=tk.LEFT, padx=(10, 5))
        
        ttk.Button(toolbar, text="📋 Paste", command=self.add_pasted_slide,
                  style='Action.TButton').pack(side=tk.LEFT, padx=5)
        
        ttk.Button(toolbar, text="⎘ Duplicate", command=self.duplicate_selected,
                  style='Action.TButton').pack(side=tk.LEFT, padx=5)
        
        ttk.Button(toolbar, text="✗ Remove", command=self.remove_selected_slides,
                  style='Action.TButton').pack(side=tk.LEFT, padx=5)
        
        ttk.Button(toolbar, text="⌧ Clear All", command=self.clear_all_slides,
                  style='Action.TButton').pack(side=tk.LEFT, padx=5)
        
        # Slides container with scrollbar
        container_frame = ttk.Frame(panel)
        container_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create canvas and scrollbar
        self.slides_canvas = tk.Canvas(container_frame, bg='#f5f5f5', 
                                      highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(container_frame, orient="vertical", 
                                 command=self.slides_canvas.yview)
        
        self.slides_canvas.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.slides_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Frame inside canvas for slides
        self.slides_container = tk.Frame(self.slides_canvas, bg='#f5f5f5')
        self.canvas_window = self.slides_canvas.create_window(
            (0, 0), 
            window=self.slides_container,
            anchor='nw'
        )
        
        # Bind resize
        self.slides_container.bind('<Configure>', self.on_slides_configure)
        self.slides_canvas.bind('<Configure>', self.on_canvas_configure)
        
        # Mouse wheel scrolling
        self.slides_canvas.bind_all("<MouseWheel>", self.on_mousewheel)
        self.slides_canvas.bind_all("<Button-4>", self.on_mousewheel)  # Linux
        self.slides_canvas.bind_all("<Button-5>", self.on_mousewheel)  # Linux
        
        # Drop zone label (shown when empty)
        self.drop_zone_label = tk.Label(
            self.slides_container,
            text="⬇ Drop HTML files here\nor click '➕ Add' to get started",
            font=('Helvetica', 14),
            foreground='#999999',
            bg='#f5f5f5',
            justify='center'
        )
        
        return panel
        
    def setup_log_panel(self, parent):
        """Create the log/console panel."""
        panel = ttk.Frame(parent)
        
        # Toolbar
        toolbar = ttk.Frame(panel)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(toolbar, text="Log:", font=('Helvetica', 11, 'bold')).pack(side=tk.LEFT)
        
        ttk.Button(toolbar, text="⌧ Clear", command=self.clear_log).pack(side=tk.RIGHT)
        
        # Log text area
        self.log_text = scrolledtext.ScrolledText(panel, wrap=tk.WORD, 
                                                   font=('Consolas', 9),
                                                   background='#f5f5f5',
                                                   height=20)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Configure tags for colored output
        self.log_text.tag_config('info', foreground='black')
        self.log_text.tag_config('success', foreground='green', font=('Consolas', 9, 'bold'))
        self.log_text.tag_config('error', foreground='red', font=('Consolas', 9, 'bold'))
        self.log_text.tag_config('warning', foreground='orange')
        self.log_text.tag_config('debug', foreground='gray')
        
        return panel
        
    def setup_footer(self, parent):
        """Create footer with action buttons."""
        footer = ttk.Frame(parent)
        footer.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(10, 0))
        footer.columnconfigure(0, weight=1)
        
        # Progress bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(footer, variable=self.progress_var, 
                                           maximum=100, mode='determinate')
        self.progress_bar.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Status label
        self.status_var = tk.StringVar(value="Ready • Drop files to add slides")
        status_label = ttk.Label(footer, textvariable=self.status_var, foreground='gray')
        status_label.grid(row=1, column=0, sticky=tk.W)
        
        # Action buttons
        button_frame = ttk.Frame(footer)
        button_frame.grid(row=1, column=1, sticky=tk.E)
        
        ttk.Button(button_frame, text="⚙ Settings", 
                  command=self.show_settings).pack(side=tk.LEFT, padx=5)
        
        self.convert_button = ttk.Button(button_frame, text="🚀 Convert to PDF", 
                                        command=self.start_conversion,
                                        style='Primary.TButton')
        self.convert_button.pack(side=tk.LEFT, padx=5)
        
    def setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        # File operations
        self.root.bind('<Control-o>', lambda e: self.add_file_slides())
        self.root.bind('<Control-v>', lambda e: self.add_pasted_slide())
        self.root.bind('<Control-s>', lambda e: self.start_conversion())
        self.root.bind('<Control-comma>', lambda e: self.show_settings())
        
        # Edit operations
        self.root.bind('<Control-a>', lambda e: self.select_all_slides())
        self.root.bind('<Escape>', lambda e: self.deselect_all_slides())
        self.root.bind('<Control-d>', lambda e: self.duplicate_selected())
        self.root.bind('<Delete>', lambda e: self.remove_selected_slides())
        
        # View operations
        self.root.bind('<F5>', lambda e: self.update_slides_display())
        
    def setup_drag_drop(self):
        """Setup drag and drop for files."""
        try:
            # Drop target for the entire window
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind('<<Drop>>', self.on_drop_files)
            
            # Also register for canvas
            self.slides_canvas.drop_target_register(DND_FILES)
            self.slides_canvas.dnd_bind('<<Drop>>', self.on_drop_files)
            
        except Exception as e:
            self.log(f"Drag & drop not available: {e}", 'warning')
            
    def on_drop_files(self, event):
        """Handle file drop."""
        files = self.root.tk.splitlist(event.data)
        html_files = [f for f in files if f.lower().endswith(('.html', '.htm'))]
        
        if html_files:
            for file_path in html_files:
                self.add_single_file(file_path)
            self.update_slides_display()
        else:
            messagebox.showwarning("No HTML Files", "Please drop HTML (.html or .htm) files.")
            
    # ===========================
    # Slide Management
    # ===========================
    
    def add_file_slides(self):
        """Add HTML slides from files."""
        files = filedialog.askopenfilenames(
            title="Select HTML files",
            filetypes=[("HTML files", "*.html *.htm"), ("All files", "*.*")],
            initialdir=self.settings.get('default_output_folder')
        )
        
        if not files:
            return
            
        for file_path in files:
            self.add_single_file(file_path)
            
        self.update_slides_display()
        
    def add_single_file(self, file_path: str):
        """Add a single HTML file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            self.slide_counter += 1
            slide = Slide(self.slide_counter, content, os.path.basename(file_path))
            self.slides.append(slide)
            self.settings.add_recent_file(file_path)
            self.log(f"Added: {os.path.basename(file_path)}", 'info')
            
        except Exception as e:
            self.log(f"Error reading {file_path}: {e}", 'error')
            
    def add_pasted_slide(self):
        """Add a slide from pasted HTML content."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Paste HTML Content")
        dialog.geometry("700x550")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Paste your HTML content below:", 
                 font=('Helvetica', 10, 'bold')).pack(pady=10, padx=10)
        
        text_area = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, 
                                             font=('Consolas', 10))
        text_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text_area.focus()
        
        # Try to paste from clipboard
        try:
            clipboard_content = self.root.clipboard_get()
            if clipboard_content and '<' in clipboard_content:
                text_area.insert('1.0', clipboard_content)
        except:
            pass
        
        def save_pasted():
            content = text_area.get('1.0', tk.END).strip()
            if not content:
                messagebox.showwarning("Empty Content", "Please paste some HTML content.")
                return
                
            self.slide_counter += 1
            slide = Slide(self.slide_counter, content, "pasted")
            self.slides.append(slide)
            self.log(f"Added pasted slide #{self.slide_counter}", 'info')
            self.update_slides_display()
            dialog.destroy()
            
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(button_frame, text="Add Slide", command=save_pasted,
                  style='Primary.TButton').pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT)
        
    def duplicate_selected(self):
        """Duplicate selected slides."""
        if not self.selected_indices:
            messagebox.showinfo("No Selection", "Please select slides to duplicate.")
            return
            
        # Sort in reverse to maintain indices
        for index in sorted(self.selected_indices, reverse=True):
            if 0 <= index < len(self.slides):
                self.duplicate_slide(index)
                
    def duplicate_slide(self, index: int):
        """Duplicate a specific slide."""
        if 0 <= index < len(self.slides):
            original = self.slides[index]
            self.slide_counter += 1
            
            new_slide = Slide(
                self.slide_counter,
                original.content,
                f"{original.filename} (copy)"
            )
            
            self.slides.insert(index + 1, new_slide)
            self.log(f"Duplicated: {original.filename}", 'info')
            self.update_slides_display()
            
    def remove_selected_slides(self):
        """Remove selected slides."""
        if not self.selected_indices:
            messagebox.showinfo("No Selection", "Please select slides to remove.")
            return
            
        count = len(self.selected_indices)
        if messagebox.askyesno("Confirm Delete", 
                              f"Remove {count} selected slide(s)?"):
            # Sort in reverse to maintain indices
            for index in sorted(self.selected_indices, reverse=True):
                if 0 <= index < len(self.slides):
                    removed = self.slides.pop(index)
                    self.log(f"Removed: {removed.filename}", 'info')
                    
            self.selected_indices.clear()
            self.update_slides_display()
            
    def remove_slide_at_index(self, index: int):
        """Remove a specific slide."""
        if 0 <= index < len(self.slides):
            slide = self.slides[index]
            if messagebox.askyesno("Confirm Delete", f"Remove slide: {slide.filename}?"):
                self.slides.pop(index)
                self.log(f"Removed: {slide.filename}", 'info')
                self.selected_indices.discard(index)
                self.update_slides_display()
                
    def clear_all_slides(self):
        """Clear all slides."""
        if not self.slides:
            return
            
        if messagebox.askyesno("Confirm Clear", 
                              f"Remove all {len(self.slides)} slides?"):
            self.slides.clear()
            self.selected_indices.clear()
            self.log("Cleared all slides", 'info')
            self.update_slides_display()
            
    def select_all_slides(self):
        """Select all slides."""
        self.selected_indices = set(range(len(self.slides)))
        self.update_selection_display()
        self.log(f"Selected all {len(self.slides)} slides", 'debug')
        
    def deselect_all_slides(self):
        """Deselect all slides."""
        self.selected_indices.clear()
        self.update_selection_display()
        
    def select_slide(self, index: int, ctrl_pressed: bool = False):
        """Select a slide (with Ctrl support for multi-select)."""
        if ctrl_pressed:
            # Toggle selection
            if index in self.selected_indices:
                self.selected_indices.remove(index)
            else:
                self.selected_indices.add(index)
        else:
            # Single selection
            self.selected_indices = {index}
            
        self.update_selection_display()
        self.log(f"Selected: {len(self.selected_indices)} slide(s)", 'debug')
        self.update_status(f"{len(self.slides)} slide(s) • {len(self.selected_indices)} selected")
        
    def update_selection_display(self):
        """Update visual selection state."""
        for i, card in enumerate(self.slide_cards):
            card.set_selected(i in self.selected_indices)
            
    def move_slide(self, from_index: int, to_index: int):
        """Move a slide from one position to another."""
        if from_index == to_index:
            return
            
        if 0 <= from_index < len(self.slides) and 0 <= to_index < len(self.slides):
            # Move the slide
            slide = self.slides.pop(from_index)
            self.slides.insert(to_index, slide)
            
            self.log(f"Moved slide from position {from_index + 1} to {to_index + 1}", 'info')
            
            # Update selection
            new_selected = set()
            for idx in self.selected_indices:
                if idx == from_index:
                    new_selected.add(to_index)
                elif from_index < idx <= to_index:
                    new_selected.add(idx - 1)
                elif to_index <= idx < from_index:
                    new_selected.add(idx + 1)
                else:
                    new_selected.add(idx)
            self.selected_indices = new_selected
                
            self.update_slides_display()
            
    def show_drop_indicator(self, target_index: int):
        """Show visual indicator for drop target."""
        # This could be enhanced with a visual line/highlight
        # For now, just highlight the target card
        pass
        
    def hide_drop_indicator(self):
        """Hide drop indicator."""
        pass
            
    def preview_slide_at_index(self, index: int):
        """Preview a specific slide."""
        if 0 <= index < len(self.slides):
            slide = self.slides[index]
            
            # Create a temporary HTML file
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.html', 
                                                    delete=False, encoding='utf-8')
            temp_file.write(slide.content)
            temp_file.close()
            
            # Open in default browser
            import webbrowser
            webbrowser.open('file://' + temp_file.name)
            
            self.log(f"Preview: {slide.filename}", 'info')
            
    def update_slides_display(self):
        """Update the slides display."""
        # Clear existing cards
        for card in self.slide_cards:
            card.destroy()
        self.slide_cards.clear()
        
        # Show drop zone if no slides
        if not self.slides:
            self.drop_zone_label.pack(expand=True, pady=100)
            self.update_status("Ready • Drop files to add slides")
            return
        else:
            self.drop_zone_label.pack_forget()
            
        # Create grid of slide cards
        self.create_slide_grid()
            
        # Update status
        self.update_status(f"{len(self.slides)} slide(s) • {len(self.selected_indices)} selected")
        
    def create_slide_grid(self):
        """Create a grid view of slides."""
        # Calculate columns based on available width
        self.root.update_idletasks()
        canvas_width = max(self.slides_canvas.winfo_width(), 600)
        
        card_width = 180
        card_height = 200
        padding = 15
        
        cols = max(1, (canvas_width - padding) // (card_width + padding))
        
        for i, slide in enumerate(self.slides):
            row = i // cols
            col = i % cols
            
            card = SlideCard(self.slides_container, slide, i, self)
            card.grid(row=row, column=col, padx=padding, pady=padding, sticky='n')
            
            # Set fixed size
            card.config(width=card_width, height=card_height)
            card.grid_propagate(False)
            
            self.slide_cards.append(card)
            
        # Configure grid weights for better spacing
        for col in range(cols):
            self.slides_container.grid_columnconfigure(col, weight=0, minsize=card_width)
            
        # Update selection
        self.update_selection_display()
        
    # ===========================
    # PDF Conversion
    # ===========================
    
    def start_conversion(self):
        """Start the PDF conversion process."""
        if not self.slides:
            messagebox.showwarning("No Slides", "Please add at least one slide before converting.")
            return
            
        if self.is_processing:
            messagebox.showwarning("Processing", "Conversion is already in progress.")
            return
            
        # Ask for output file
        default_folder = self.settings.get('default_output_folder')
        output_file = filedialog.asksaveasfilename(
            title="Save PDF as",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
            initialfile=f"presentation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            initialdir=default_folder
        )
        
        if not output_file:
            return
            
        self.output_pdf_path = output_file
        self.is_processing = True
        self.convert_button.config(state='disabled')
        
        # Run conversion in a separate thread to avoid blocking UI
        thread = Thread(target=self.run_conversion_async, daemon=True)
        thread.start()
        
    def run_conversion_async(self):
        """Run the async conversion in a new event loop."""
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.convert_slides_to_pdf())
        except Exception as e:
            self.log(f"Conversion failed: {e}", 'error')
            self.root.after(0, lambda: messagebox.showerror("Error", f"Conversion failed:\n{e}"))
        finally:
            self.is_processing = False
            self.root.after(0, lambda: self.convert_button.config(state='normal'))
            
    async def convert_slides_to_pdf(self):
        """Main conversion process using Playwright."""
        self.log("=" * 50, 'info')
        self.log("Starting PDF conversion...", 'success')
        self.update_status("Initializing browser...")
        
        # Create temporary directory for intermediate files
        self.temp_dir = tempfile.mkdtemp(prefix='html2pdf_')
        self.log(f"Temp directory: {self.temp_dir}", 'debug')
        
        try:
            # Get quality settings
            quality = self.settings.get('pdf_quality', 'high')
            scale_factor = {'high': 2, 'medium': 1.5, 'low': 1}.get(quality, 2)
            
            async with async_playwright() as p:
                # Launch browser
                self.log(f"Launching browser (quality: {quality})...", 'info')
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    viewport=None,
                    device_scale_factor=scale_factor
                )
                
                total_slides = len(self.slides)
                
                # Process each slide
                for i, slide in enumerate(self.slides, 1):
                    self.update_progress((i - 0.5) / total_slides * 80)
                    self.update_status(f"Processing slide {i}/{total_slides}: {slide.filename}")
                    
                    await self.process_slide(context, slide, i)
                    
                    self.update_progress(i / total_slides * 80)
                    
                await browser.close()
                
            # Merge PDFs
            self.update_status("Merging PDFs...")
            self.update_progress(85)
            self.merge_pdfs()
            
            # Success
            self.update_progress(100)
            self.update_status("Conversion complete!")
            self.log("=" * 50, 'info')
            self.log(f"✓ PDF created: {self.output_pdf_path}", 'success')
            self.log("=" * 50, 'info')
            
            self.root.after(0, lambda: messagebox.showinfo(
                "Success", 
                f"PDF created successfully!\n\n{len(self.slides)} slides converted\n\nSaved to:\n{self.output_pdf_path}"
            ))
            
            # Auto-open if enabled
            if self.settings.get('auto_open_pdf'):
                self.open_file(self.output_pdf_path)
                
        except Exception as e:
            self.log(f"Error: {e}", 'error')
            import traceback
            self.log(traceback.format_exc(), 'debug')
            raise
        finally:
            self.cleanup_temp_files()
            self.update_progress(0)

    # --- FUNCTION WITH APPLIED FIXES ---
    async def process_slide(self, context, slide: Slide, slide_number: int):
        """Process a single slide: detect dimensions and create PDF."""
        self.log(f"\n--- Slide {slide_number}: {slide.filename} ---", 'info')
        
        temp_html = os.path.join(self.temp_dir, f'slide_{slide_number}.html')
        html_content = self.prepare_html_for_pdf(slide.content)
        
        with open(temp_html, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        page = await context.new_page()
        
        try:
            # Set a very large initial viewport height. This allows flexbox elements
            # to expand to their full natural height without being constrained.
            await page.set_viewport_size({"width": 1920, "height": 10800})

            await page.goto(f'file://{temp_html}', wait_until='networkidle', timeout=30000)
            
            # Additional waits to ensure everything is rendered
            await page.evaluate("() => document.fonts.ready")
            await page.evaluate("""
                () => Promise.all(
                    Array.from(document.images)
                        .filter(img => !img.complete)
                        .map(img => new Promise(resolve => {
                            img.onload = img.onerror = resolve;
                        }))
                )
            """)
            await asyncio.sleep(0.5) # A slightly longer sleep for complex layouts
            
            # Detect dimensions using a more robust JS snippet
            dimensions = await page.evaluate("""
                () => {
                    // Prefer the .slide-container if it exists, otherwise fall back to body
                    const container = document.querySelector('.slide-container') || document.body;
                    const width = Math.ceil(container.scrollWidth);
                    const height = Math.ceil(container.scrollHeight);
                    return { width, height };
                }
            """)
            
            width = min(max(dimensions['width'], 800), 14400)
            height = min(max(dimensions['height'], 600), 14400)
            
            slide.width = width
            slide.height = height
            
            self.log(f"Dimensions detected: {width}×{height}px", 'info')
            
            # Inject CSS for exact sizing for printing
            await page.evaluate(f"""
                () => {{
                    const style = document.createElement('style');
                    style.textContent = `
                        @page {{ size: {width}px {height}px; margin: 0; }}
                        html, body {{
                            width: {width}px !important;
                            height: {height}px !important;
                            margin: 0 !important;
                            padding: 0 !important;
                            overflow: hidden !important;
                        }}
                        * {{ 
                            page-break-after: avoid !important; 
                            page-break-before: avoid !important;
                            page-break-inside: avoid !important; 
                        }}
                    `;
                    document.head.appendChild(style);
                }}
            """)
            
            await asyncio.sleep(0.2)
            
            # Generate PDF
            pdf_path = os.path.join(self.temp_dir, f'slide_{slide_number}.pdf')
            
            # Use prefer_css_page_size=True to respect our @page rule
            await page.pdf(
                path=pdf_path,
                print_background=True,
                margin={'top': '0', 'right': '0', 'bottom': '0', 'left': '0'},
                prefer_css_page_size=True, # This is more reliable with our injected CSS
                display_header_footer=False,
                page_ranges='1'
            )
            
            slide.pdf_path = pdf_path
            self.log(f"✓ PDF generated", 'success')
            
            # Update card dimensions display
            self.root.after(0, lambda idx=slide_number-1: self.update_card_dimensions(idx))
            
        finally:
            await page.close()
        
    def update_card_dimensions(self, index: int):
        """Update a card's dimensions display."""
        if 0 <= index < len(self.slide_cards):
            self.slide_cards[index].update_dimensions()
            
    def prepare_html_for_pdf(self, content: str) -> str:
        """Prepare HTML content for PDF generation."""
        content_lower = content.lower()
        
        if '<html' in content_lower:
            return content
            
        if '<body' in content_lower:
            return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        * {{ box-sizing: border-box; -webkit-print-color-adjust: exact; 
            print-color-adjust: exact; }}
        html {{ margin: 0; padding: 0; }}
    </style>
</head>
{content}
</html>"""
        
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        * {{ box-sizing: border-box; -webkit-print-color-adjust: exact;
            print-color-adjust: exact; }}
        html, body {{ margin: 0; padding: 0; }}
    </style>
</head>
<body>
{content}
</body>
</html>"""
        
    def merge_pdfs(self):
        """Merge all slide PDFs into one output PDF."""
        self.log("\n--- Merging PDFs ---", 'info')
        
        pdf_writer = PdfWriter()
        total_pages = 0
        
        for i, slide in enumerate(self.slides, 1):
            if not slide.pdf_path or not os.path.exists(slide.pdf_path):
                self.log(f"Warning: PDF not found for slide {i}", 'warning')
                continue
                
            try:
                pdf_reader = PdfReader(slide.pdf_path)
                page_count = len(pdf_reader.pages)
                
                if page_count > 0:
                    pdf_writer.add_page(pdf_reader.pages[0])
                    total_pages += 1
                    self.log(f"Added slide {i}: {slide.filename}", 'debug')
                    
                    if page_count > 1:
                        self.log(f"  ⚠ Skipped {page_count - 1} extra page(s)", 'warning')
                        
            except Exception as e:
                self.log(f"Error adding slide {i}: {e}", 'error')
                
        with open(self.output_pdf_path, 'wb') as output_file:
            pdf_writer.write(output_file)
            
        self.log(f"✓ Merged {len(self.slides)} slides into {total_pages} pages", 'success')
        
    # ===========================
    # Settings
    # ===========================
    
    def show_settings(self):
        """Show settings dialog."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Settings")
        dialog.geometry("500x350")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        
        # Main frame
        main_frame = ttk.Frame(dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Default output folder
        ttk.Label(main_frame, text="Default Output Folder:", 
                 font=('Helvetica', 10, 'bold')).grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        
        folder_frame = ttk.Frame(main_frame)
        folder_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 15))
        folder_frame.columnconfigure(0, weight=1)
        
        folder_var = tk.StringVar(value=self.settings.get('default_output_folder'))
        folder_entry = ttk.Entry(folder_frame, textvariable=folder_var)
        folder_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        
        def browse_folder():
            folder = filedialog.askdirectory(initialdir=folder_var.get())
            if folder:
                folder_var.set(folder)
                
        ttk.Button(folder_frame, text="Browse...", command=browse_folder).grid(row=0, column=1)
        
        # Auto-open PDF
        auto_open_var = tk.BooleanVar(value=self.settings.get('auto_open_pdf'))
        ttk.Checkbutton(main_frame, text="Automatically open PDF after conversion",
                       variable=auto_open_var).grid(row=2, column=0, sticky=tk.W, pady=5)
        
        # PDF Quality
        ttk.Label(main_frame, text="PDF Quality:", 
                 font=('Helvetica', 10, 'bold')).grid(row=3, column=0, sticky=tk.W, pady=(15, 5))
        
        quality_var = tk.StringVar(value=self.settings.get('pdf_quality'))
        quality_frame = ttk.Frame(main_frame)
        quality_frame.grid(row=4, column=0, sticky=tk.W, pady=(0, 15))
        
        ttk.Radiobutton(quality_frame, text="High (2x scale, larger file)", 
                       variable=quality_var, value='high').pack(anchor=tk.W)
        ttk.Radiobutton(quality_frame, text="Medium (1.5x scale, balanced)", 
                       variable=quality_var, value='medium').pack(anchor=tk.W)
        ttk.Radiobutton(quality_frame, text="Low (1x scale, smaller file)", 
                       variable=quality_var, value='low').pack(anchor=tk.W)
        
        # Buttons
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        def save_settings():
            self.settings.set('default_output_folder', folder_var.get())
            self.settings.set('auto_open_pdf', auto_open_var.get())
            self.settings.set('pdf_quality', quality_var.get())
            
            self.log("Settings saved", 'info')
            dialog.destroy()
            
        ttk.Button(button_frame, text="Save", command=save_settings,
                  style='Primary.TButton').pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT)
        
    # ===========================
    # Utility Methods
    # ===========================
    
    def log(self, message: str, level: str = 'info'):
        """Add a message to the log."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        formatted_message = f"[{timestamp}] {message}\n"
        
        def append_log():
            self.log_text.insert(tk.END, formatted_message, level)
            self.log_text.see(tk.END)
            
        self.root.after(0, append_log)
        
    def clear_log(self):
        """Clear the log."""
        self.log_text.delete('1.0', tk.END)
        
    def update_status(self, status: str):
        """Update status label."""
        self.root.after(0, lambda: self.status_var.set(status))
        
    def update_progress(self, value: float):
        """Update progress bar."""
        self.root.after(0, lambda: self.progress_var.set(value))
        
    def cleanup_temp_files(self):
        """Clean up temporary files."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
                self.log(f"Cleaned up temp files", 'debug')
            except Exception as e:
                self.log(f"Error cleaning up: {e}", 'warning')
                
    def open_file(self, filepath: str):
        """Open file with default application."""
        import platform
        import subprocess
        
        try:
            if platform.system() == 'Darwin':
                subprocess.call(['open', filepath])
            elif platform.system() == 'Windows':
                os.startfile(filepath)
            else:
                subprocess.call(['xdg-open', filepath])
        except Exception as e:
            self.log(f"Could not open file: {e}", 'error')
            
    def update_recent_files_menu(self):
        """Update the recent files menu."""
        self.recent_menu.delete(0, tk.END)
        
        recent_files = self.settings.get('recent_files', [])
        if not recent_files:
            self.recent_menu.add_command(label="(No recent files)", state='disabled')
        else:
            for filepath in recent_files:
                if os.path.exists(filepath):
                    filename = os.path.basename(filepath)
                    self.recent_menu.add_command(
                        label=filename,
                        command=lambda f=filepath: self.add_single_file(f) or self.update_slides_display()
                    )
                    
    def show_shortcuts(self):
        """Show keyboard shortcuts help."""
        shortcuts_text = """Keyboard Shortcuts:

File Operations:
  Ctrl+O          Add files
  Ctrl+V          Paste HTML
  Ctrl+S          Convert to PDF
  Ctrl+,          Settings

Edit Operations:
  Ctrl+A          Select all slides
  Escape          Deselect all
  Ctrl+D          Duplicate selected
  Delete          Remove selected

View Operations:
  F5              Refresh display

Mouse Operations:
  Click           Select slide
  Ctrl+Click      Multi-select (toggle)
  Double-click    Preview slide
  Right-click     Context menu
  Drag slide      Reorder slides
"""
        
        messagebox.showinfo("Keyboard Shortcuts", shortcuts_text)
        
    def show_about(self):
        """Show about dialog."""
        about_text = """HTML Presentation to PDF Converter
Version 2.4.0 - Corrected Edition

A production-ready application for converting HTML slides 
to a merged PDF document.

Features:
✓ Drag & drop files to add
✓ Drag slides to reorder
✓ Click to select (Ctrl for multi-select)
✓ Hover effects for better UX
✓ Keyboard shortcuts
✓ Batch operations
✓ Settings panel
✓ Recent files

Built with: Python, Tkinter, Playwright, PyPDF

© 2024"""
        
        messagebox.showinfo("About", about_text)
        
    def on_window_configure(self, event):
        """Handle window resize/move."""
        if event.widget == self.root:
            # Save window size
            if not self.root.state() == 'zoomed':  # Not maximized
                self.settings.set('window_width', self.root.winfo_width())
                self.settings.set('window_height', self.root.winfo_height())
                
    def on_slides_configure(self, event):
        """Handle slides container resize."""
        self.slides_canvas.configure(scrollregion=self.slides_canvas.bbox("all"))
        
    def on_canvas_configure(self, event):
        """Handle canvas resize."""
        # Update canvas window width to match canvas
        self.slides_canvas.itemconfig(self.canvas_window, width=event.width)
        
    def on_mousewheel(self, event):
        """Handle mouse wheel scrolling."""
        # Windows and MacOS
        if event.num == 5 or event.delta < 0:
            self.slides_canvas.yview_scroll(1, "units")
        elif event.num == 4 or event.delta > 0:
            self.slides_canvas.yview_scroll(-1, "units")
            
    def on_closing(self):
        """Handle application close."""
        if self.is_processing:
            if not messagebox.askyesno("Confirm Exit", 
                                      "Conversion in progress. Exit anyway?"):
                return
        
        self.cleanup_temp_files()
        self.root.destroy()


def main():
    """Main entry point."""
    if sys.version_info < (3, 7):
        print("This application requires Python 3.7 or higher.")
        sys.exit(1)
        
    # Create app with DnD support
    root = TkinterDnD.Tk()
    app = PDFConverterApp(root)
    
    # Center window
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f'{width}x{height}+{x}+{y}')
    
    root.mainloop()


if __name__ == '__main__':
    main()
