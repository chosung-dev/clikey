import tkinter as tk
from tkinter import Canvas
import pyautogui
from PIL import Image, ImageTk, ImageDraw
from typing import Optional, Callable


class Magnifier:
    def __init__(self, parent: tk.Widget, zoom_factor: int = 10, size: int = 150):
        """
        Initialize magnifier window.
        
        Args:
            parent: Parent window
            zoom_factor: How much to zoom the area (default 10x)
            size: Size of the magnifier window in pixels
        """
        self.parent = parent
        self.zoom_factor = zoom_factor
        self.size = size
        self.magnifier_window = None
        self.canvas = None
        self.running = False
        self.capture_area = 20  # Size of area to capture around cursor
        
        # Callbacks
        self.on_click_callback: Optional[Callable[[int, int], None]] = None
        
    def show(self, on_click_callback: Optional[Callable[[int, int], None]] = None):
        """Show the magnifier window."""
        if self.magnifier_window:
            return
            
        self.on_click_callback = on_click_callback
        self.running = True
        
        # Create magnifier window
        self.magnifier_window = tk.Toplevel(self.parent)
        self.magnifier_window.title("색상 돋보기")
        self.magnifier_window.geometry(f"{self.size}x{self.size}")
        self.magnifier_window.resizable(False, False)
        self.magnifier_window.attributes("-topmost", True)
        self.magnifier_window.overrideredirect(True)  # Remove window decorations

        # Create canvas for magnified view
        self.canvas = Canvas(
            self.magnifier_window,
            width=self.size,
            height=self.size,
            bg="black",
            highlightthickness=2,
            highlightbackground="red"
        )
        self.canvas.pack()
        
        # Bind events
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        # Don't bind keyboard events to avoid stealing focus
        # self.magnifier_window.bind("<Escape>", lambda e: self.hide())
        # self.magnifier_window.bind("<KeyPress>", self._on_key_press)
        # Don't steal focus from parent window
        # self.magnifier_window.focus_set()
        
        # Start updating
        self._update_magnifier()
        
    def hide(self):
        """Hide the magnifier window."""
        self.running = False
        if self.magnifier_window:
            self.magnifier_window.destroy()
            self.magnifier_window = None
            self.canvas = None
            
    def _update_magnifier(self):
        """Update the magnified view."""
        if not self.running or not self.magnifier_window:
            return
            
        try:
            # Get current mouse position
            mouse_x, mouse_y = pyautogui.position()
            
            # Position magnifier window near cursor but not blocking it
            mag_x = mouse_x + 30
            mag_y = mouse_y - self.size - 50
            
            # Keep magnifier on screen
            screen_width = self.magnifier_window.winfo_screenwidth()
            screen_height = self.magnifier_window.winfo_screenheight()
            
            if mag_x + self.size > screen_width:
                mag_x = mouse_x - self.size - 30
            if mag_y < 0:
                mag_y = mouse_y + 30
                
            self.magnifier_window.geometry(f"{self.size}x{self.size}+{mag_x}+{mag_y}")
            
            # Capture area around cursor
            capture_x = max(0, mouse_x - self.capture_area // 2)
            capture_y = max(0, mouse_y - self.capture_area // 2)
            
            # Take screenshot of small area
            screenshot = pyautogui.screenshot(
                region=(capture_x, capture_y, self.capture_area, self.capture_area)
            )
            
            # Convert to PIL Image and resize
            pil_image = screenshot
            zoomed_image = pil_image.resize(
                (self.size, self.size), 
                Image.NEAREST  # Use nearest neighbor for pixel-perfect zoom
            )
            
            # Draw crosshair
            draw = ImageDraw.Draw(zoomed_image)
            center = self.size // 2
            crosshair_size = 10
            crosshair_color = "red"
            
            # Horizontal line
            draw.line(
                [(center - crosshair_size, center), (center + crosshair_size, center)],
                fill=crosshair_color,
                width=2
            )
            # Vertical line
            draw.line(
                [(center, center - crosshair_size), (center, center + crosshair_size)],
                fill=crosshair_color,
                width=2
            )
            
            # Convert to PhotoImage and display
            self.photo = ImageTk.PhotoImage(zoomed_image)
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
            
        except Exception as e:
            print(f"Magnifier update error: {e}")
            
        # Schedule next update
        if self.running:
            self.magnifier_window.after(50, self._update_magnifier)
            
    def _on_canvas_click(self, event):
        """Handle click on magnified canvas."""
        if self.on_click_callback:
            # Get current mouse position (this is where user wants to capture)
            mouse_x, mouse_y = pyautogui.position()
            self.on_click_callback(mouse_x, mouse_y)