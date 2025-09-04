# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is "Namaan's Macro" - a Tkinter-based macro editor and execution tool for Windows. It allows users to create, edit, and execute automated sequences of mouse clicks, keyboard inputs, time delays, and conditional logic based on screen pixel colors.

## Architecture

### Core Structure
- `app.py` - Main entry point, initializes Tkinter UI and handles cleanup
- `ui/` - User interface components
  - `main_window.py` - Main UI window with menu, layout, and file operations
  - `macro_list.py` - Macro list management with drag & drop, copy/paste
  - `styled_list.py` - Custom listbox widget for macro step display
  - `dialogs/` - Dialog windows
    - `settings.py` - Settings dialog (repeat count, delays, hotkeys, beep)
    - `input_dialogs.py` - Keyboard, mouse, and delay input dialogs
    - `condition_dialog.py` - Image condition creation dialog
  - `execution/` - Macro execution engine
    - `executor.py` - Core macro execution logic with threading
    - `highlighter.py` - Visual feedback during execution
- `core/` - Core functionality modules  
  - `state.py` - Default settings and hotkey configurations
  - `persistence.py` - JSON file I/O for macro data and app state
  - `keyboard_hotkey.py` - Keyboard hotkey registration (F8/F9 by default)
  - `mouse.py` - Mouse automation using AutoIt/PyAutoGUI
  - `screen.py` - Screen capture and pixel color detection
- `utils/` - Utility modules
  - `drag_drop.py` - Drag and drop functionality for macro list
  - `inline_edit.py` - Inline editing of macro step descriptions

### Macro Data Format
Macros are stored as JSON with this structure:
```json
{
  "version": 1,
  "items": ["마우스:이동 100,200", "시간:1.5", "조건: 픽셀(500,400) == (255,255,255)", "  키보드:입력 hello", "조건끝"],
  "settings": {"repeat": 1, "start_delay": 3, "beep_on_finish": false},
  "hotkeys": {"start": "F8", "stop": "F9"}
}
```

Macro commands use Korean prefixes:
- `마우스:` - Mouse actions (이동=move, 클릭=click)
- `키보드:` - Keyboard actions (입력=input, 누름=press)  
- `시간:` - Time delays in seconds (supports decimal)
- `조건:` - Conditional logic based on pixel colors
- `매크로중지` - Stop execution block

## Development Commands

### Setup
```bash
# Create virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

### Running the Application
```bash
python app.py
```

### Building Executable
```bash
# Build with PyInstaller using the spec file
pyinstaller --noconfirm --clean ExecutableFile.spec

# Build with custom app name
pyinstaller --noconfirm --clean ExecutableFile.spec -- --app-name "CustomName"
```

The executable will be created in the `dist/` folder.

## Key Dependencies
- `tkinter` - GUI framework
- `pyautogui` - Cross-platform automation
- `pyautoit` - Windows-specific automation (preferred when available)
- `keyboard` - Global hotkey registration
- `pillow` - Screen capture and image processing
- `pyinstaller` - Executable creation

## Platform Requirements
- **Primary Platform**: Windows (requires administrator privileges for automation)
- **Python**: 3.12+
- AutoIt functionality only works on Windows

## Important Notes
- The application may require administrator privileges for mouse/keyboard automation
- Global hotkeys (F8 start, F9 stop) are registered when the `keyboard` library is available
- App state (last opened file) is saved to `~/.namaans_macro/app_state.json`
- UI text and macro commands are in Korean
- Failsafe is enabled in PyAutoGUI - moving mouse to top-left corner will stop execution

## Testing and Quality Assurance
- No formal test suite is present in this codebase
- Application requires manual testing through UI interaction
- Testing typically involves verifying macro execution, file I/O, and UI responsiveness
- Run the application with `python app.py` for manual testing

## Code Style and Conventions
- Mixed Korean/English codebase with Korean UI text and macro commands
- Uses standard Python naming conventions (snake_case for functions/variables)
- Tkinter-based GUI following standard widget patterns
- JSON-based data persistence with version field for future compatibility

## 개발 시 항상 지켜야 할 원칙
- **성능**
  - 하위버전 호환성 고려 하지 않을 것
  - Exception 발생 시 반드시 로그를 남기고, 사용자 친화적인 메시지로 변환.