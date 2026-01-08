# DS2 CCM Font Editor

A modern graphical editor for **Dark Souls II** (and Scholar of the First Sin) **.ccm** font files.

This tool allows you to load, view, edit, add/remove glyphs, preview associated texture files (PNG/DDS), export/import to a human-readable text format, and save modified CCM files. Perfect for modders working on custom fonts, translations, or UI modifications.

## Features
- Full CCM file loading and saving
- Editable table with all glyph parameters (code, texture ID, prespace, width, advance, tex regions)
- Add and delete glyphs
- Export/import glyphs to/from plain text for easy editing or diffing
- Automatic detection and preview of associated textures:
  - `filename.png` / `filename.dds` → texture 0
  - `filename_1.png`, `filename_0001.png`, etc. → additional textures
- Modern dark-themed UI (Dracula-inspired)
- Detailed logging for debugging (`ccm_editor_detailed.log`)
- Debug tools: header info, full file hex dump

## Installation

bash
git clone https://github.com/yourusername/DS2-CCM-Font-Editor.git
cd DS2-CCM-Font-Editor
pip install -r requirements.txt
python main.py


> Rename your main script to `main.py` or adjust the run command accordingly.

## Usage
1. Click **Load CCM** and select a `.ccm` file (usually found in `menu/font` folder of the game).
2. The tool automatically searches for matching texture files in the same directory.
3. Edit glyph values directly in the table or use **Add Glyph** / **Delete Glyph**.
4. Use **Export to Text** for batch editing or backups, then **Import from Text** to apply changes.
5. Save modifications with **Save CCM**.

## Screenshots
*(Add screenshots of the UI here once available – recommended for better visibility on GitHub)*

## TODO / Planned Features
- Direct texture preview with glyph region highlighting
- Full DDS support with thumbnail generation
- Glyph preview/rendering on texture
- Drag-and-drop tex region editing on the texture preview
- Batch processing for multiple CCM files

## Contributing
Contributions are very welcome! Feel free to:
- Report bugs or suggest features via Issues
- Submit Pull Requests with improvements or new features
- Help improve the UI or add missing functionality

## License
This project is licensed under the **MIT License** – see the [LICENSE](LICENSE) file for details.

---

Made with ❤️ for the Dark Souls modding community.
