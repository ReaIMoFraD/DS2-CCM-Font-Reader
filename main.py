import sys
from PyQt5.QtGui import QColor
import struct
import os
import logging
import binascii
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QFileDialog, QTableWidget, QTableWidgetItem, 
                             QLabel, QInputDialog, QMessageBox, QTextEdit)
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt
from PIL import Image

# Setup logging with detailed format
logging.basicConfig(
    filename='ccm_editor_detailed.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
)
logger = logging.getLogger(__name__)

class TexRegion:
    def __init__(self, x1, y1, x2, y2):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2

class Glyph:
    def __init__(self, code, index, texture_id, prespace, width, advance, tex_region):
        self.code = code
        self.index = index
        self.texture_id = texture_id
        self.prespace = prespace
        self.width = width
        self.advance = advance
        self.tex_region = tex_region

class CCMFont:
    def __init__(self):
        self.format = 0
        self.file_size = 0
        self.font_height = 0
        self.texture_width = 0
        self.texture_height = 0
        self.tex_region_count = 0
        self.glyph_count = 0
        self.tex_region_offset = 0
        self.glyph_offset = 0
        self.alignment = 0
        self.texture_count = 1  # Default from FNT
        self.glyphs = []
        self.filename = ""
        self.raw_data = b""  # Store raw file data for debugging

    def load_file(self, file_path):
        try:
            with open(file_path, 'rb') as f:
                self.raw_data = f.read()
            file_size = len(self.raw_data)
            logger.debug(f"Loading CCM file: {file_path}, size: {file_size} bytes")

            # Parse header (matches C++ CCM2 struct)
            header_format = '<I I H H H H H 2s I I H H'  # 36 bytes
            header_size = struct.calcsize(header_format)
            if file_size < header_size:
                return False, "File too small for header"
            header = struct.unpack(header_format, self.raw_data[:header_size])
            (
                self.format, self.file_size, self.font_height, self.texture_width, self.texture_height,
                self.tex_region_count, self.glyph_count, pad,
                self.tex_region_offset, self.glyph_offset, self.alignment, self.texture_count
            ) = header
            logger.debug(f"Header parsed: format={hex(self.format)}, file_size={self.file_size}, "
                         f"font_height={self.font_height}, texture_width={self.texture_width}, "
                         f"texture_height={self.texture_height}, tex_region_count={self.tex_region_count}, "
                         f"glyph_count={self.glyph_count}, "
                         f"tex_region_offset={self.tex_region_offset}, glyph_offset={self.glyph_offset}, "
                         f"alignment={self.alignment}, texture_count={self.texture_count}")
            logger.debug(f"Raw header bytes: {binascii.hexlify(self.raw_data[:header_size]).decode()}")

            # Validate header
            if self.format != 0x20000:
                error_msg = f"Invalid CCM format: {hex(self.format)}, expected 0x20000"
                logger.error(error_msg)
                return False, error_msg
            if self.file_size > file_size:
                error_msg = f"File size mismatch: header claims {self.file_size}, actual {file_size}"
                logger.error(error_msg)
                return False, error_msg
            if self.tex_region_offset < header_size or self.glyph_offset < header_size:
                error_msg = f"Invalid offsets: tex_region_offset={self.tex_region_offset}, glyph_offset={self.glyph_offset}"
                logger.error(error_msg)
                return False, error_msg

            # Parse TexRegions
            self.glyphs = []
            tex_region_format = '<hhhh'
            tex_region_size = struct.calcsize(tex_region_format)
            tex_regions = []
            for i in range(self.tex_region_count):
                offset = self.tex_region_offset + i * tex_region_size
                tex_region = struct.unpack(tex_region_format, self.raw_data[offset:offset+tex_region_size])
                tex_regions.append(TexRegion(*tex_region))

            # Parse Glyphs
            glyph_format = '<I I h h h h i i'  # code, texRegionOffset, textureIndex, preSpace, width, advance, iVar10, iVar14
            glyph_size = struct.calcsize(glyph_format)
            logger.debug(f"Using glyph format: {glyph_format}, size: {glyph_size} bytes")

            for i in range(self.glyph_count):
                offset = self.glyph_offset + i * glyph_size
                glyph_data = struct.unpack(glyph_format, self.raw_data[offset:offset+glyph_size])
                code, tex_region_offset, texture_id, prespace, width, advance, iVar10, iVar14 = glyph_data
                logger.debug(f"Glyph {i}: code={code}, tex_region_offset={tex_region_offset}, "
                             f"texture_id={texture_id}, prespace={prespace}, width={width}, "
                             f"advance={advance}, iVar10={iVar10}, iVar14={iVar14}")
                logger.debug(f"Raw glyph bytes: {binascii.hexlify(self.raw_data[offset:offset+glyph_size]).decode()}")

                if iVar10 != 0 or iVar14 != 0:
                    logger.warning(f"Glyph {i}: Non-zero iVar10={iVar10} or iVar14={iVar14}")

                # Find TexRegion index by offset
                if tex_region_offset < self.tex_region_offset or (tex_region_offset - self.tex_region_offset) % tex_region_size != 0:
                    error_msg = f"Glyph {i} has invalid texRegionOffset {tex_region_offset}"
                    logger.error(error_msg)
                    return False, error_msg
                tex_idx = (tex_region_offset - self.tex_region_offset) // tex_region_size
                if tex_idx < 0 or tex_idx >= len(tex_regions):
                    error_msg = f"Glyph {i} texRegion index {tex_idx} out of range"
                    logger.error(error_msg)
                    return False, error_msg
                tex_region_obj = tex_regions[tex_idx]
                glyph_obj = Glyph(code, i, texture_id, prespace, width, advance, tex_region_obj)
                self.glyphs.append(glyph_obj)

            # Calculate texture_count
            if self.glyphs:
                self.texture_count = max(g.texture_id for g in self.glyphs) + 1
            logger.debug(f"Calculated texture_count: {self.texture_count}")

            self.filename = file_path
            logger.info(f"Successfully loaded CCM file: {file_path} with {self.glyph_count} glyphs")
            return True, "Success"
        except Exception as e:
            return False, f"Unexpected error loading CCM file: {str(e)}"

    def save_file(self, file_path):
        try:
            header_format = '<IIHHHHHH2xIIhh'
            header_size = struct.calcsize(header_format)
            glyph_format = '<IIHHHHII'
            glyph_size = struct.calcsize(glyph_format)
            tex_region_format = '<hhhh'
            tex_region_size = struct.calcsize(tex_region_format)

            self.tex_region_count = len(self.glyphs)
            self.glyph_count = len(self.glyphs)
            self.texture_count = max((g.texture_id for g in self.glyphs), default=0) + 1

            tex_region_offset = header_size
            glyph_offset = tex_region_offset + self.tex_region_count * tex_region_size
            self.file_size = header_size + (self.tex_region_count * tex_region_size) + (self.glyph_count * glyph_size)

            data = bytearray()
            # Write header
            data += struct.pack(
                header_format,
                0x20000, self.file_size, self.font_height, self.texture_width, self.texture_height,
                self.tex_region_count, self.glyph_count,  # 2x padding is handled by format
                tex_region_offset, glyph_offset, self.alignment, self.texture_count
            )

            # Write TexRegions
            for glyph in self.glyphs:
                data += struct.pack(tex_region_format,
                    glyph.tex_region.x1, glyph.tex_region.y1,
                    glyph.tex_region.x2, glyph.tex_region.y2)

            # Write Glyphs
            for i, glyph in enumerate(self.glyphs):
                tex_region_offset_val = header_size + i * tex_region_size
                data += struct.pack(glyph_format,
                    glyph.code, tex_region_offset_val, glyph.texture_id,
                    glyph.prespace, glyph.width, glyph.advance, 0, 0)

            with open(file_path, 'wb') as f:
                f.write(data)

            logger.info(f"Saved CCM file: {file_path}, size: {len(data)} bytes")
            return True, "Success"
        except Exception as e:
            error_msg = f"Failed to save CCM file: {str(e)}"
            logger.exception(error_msg)
            return False, error_msg

    def export_to_text(self, file_path):
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"Height: {self.font_height}\n")
                f.write(f"TextureWidth: {self.texture_width}\n")
                f.write(f"TextureHeight: {self.texture_height}\n")
                f.write(f"NumTextures: {self.texture_count}\n")
                f.write(f"NumGlyphs: {self.glyph_count}\n\n")
                
                for glyph in self.glyphs:
                    f.write(f"code={glyph.code}, textureId={glyph.texture_id}, "
                           f"prespace={glyph.prespace}, width={glyph.width}, "
                           f"advance={glyph.advance}, "
                           f"top=({glyph.tex_region.x1}, {glyph.tex_region.y1}), "
                           f"bottom=({glyph.tex_region.x2}, {glyph.tex_region.y2})\n")
            
            logger.info(f"Exported to text: {file_path}")
            return True, "Success"
        except Exception as e:
            error_msg = f"Failed to export to text: {str(e)}"
            logger.exception(error_msg)
            return False, error_msg

    def import_from_text(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            self.glyphs.clear()
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("Height:"):
                    self.font_height = int(line.split(":")[1])
                elif line.startswith("TextureWidth:"):
                    self.texture_width = int(line.split(":")[1])
                elif line.startswith("TextureHeight:"):
                    self.texture_height = int(line.split(":")[1])
                elif line.startswith("NumTextures:"):
                    self.texture_count = int(line.split(":")[1])
                elif line.startswith("NumGlyphs:"):
                    self.glyph_count = int(line.split(":")[1])
                elif line.startswith("code="):
                    parts = line.split(", ")
                    code = int(parts[0].split("=")[1])
                    texture_id = int(parts[1].split("=")[1])
                    prespace = int(parts[2].split("=")[1])
                    width = int(parts[3].split("=")[1])
                    advance = int(parts[4].split("=")[1])
                    top = eval(parts[5].split("=")[1])
                    bottom = eval(parts[6].split("=")[1])
                    
                    if texture_id >= self.texture_count:
                        logger.warning(f"Invalid texture_id {texture_id} for code {code}, max {self.texture_count}")
                        continue
                    
                    tex_region = TexRegion(top[0], top[1], bottom[0], bottom[1])
                    glyph = Glyph(code, len(self.glyphs), texture_id, prespace, width, advance, tex_region)
                    self.glyphs.append(glyph)
            
            self.tex_region_count = len(self.glyphs)
            self.glyph_count = len(self.glyphs)
            logger.info(f"Imported from text: {file_path}")
            return True, "Success"
        except Exception as e:
            error_msg = f"Failed to import from text: {str(e)}"
            logger.exception(error_msg)
            return False, error_msg

    def dump_file(self):
        try:
            if not self.raw_data:
                error_msg = "No file loaded"
                logger.error(error_msg)
                return False, error_msg
            
            dump = []
            for i in range(0, len(self.raw_data), 16):
                chunk = self.raw_data[i:i+16]
                hex_part = binascii.hexlify(chunk).decode()
                ascii_part = ''.join(chr(c) if 32 <= c < 127 else '.' for c in chunk)
                dump.append(f"{i:08x}  {hex_part:<32}  {ascii_part}")
            
            logger.debug(f"File dump:\n{chr(10).join(dump)}")
            return True, '\n'.join(dump)
        except Exception as e:
            error_msg = f"Failed to dump file: {str(e)}"
            logger.exception(error_msg)
            return False, error_msg

class CCMEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CCM Font Editor")
        self.ccm = CCMFont()
        self.init_ui()

    def init_ui(self):
        # Full dark theme and custom UI
        self.setStyleSheet('''
            QMainWindow { background: #181a20; }
            QLabel, QTableWidget, QComboBox, QTextEdit { color: #f8f8f2; font-size: 15px; }
            QTableWidget { background: #23272e; alternate-background-color: #181a20; gridline-color: #44475a; border-radius: 8px; }
            QHeaderView::section { background: #282a36; color: #ffb86c; font-weight: bold; font-size: 17px; border: none; border-radius: 0px; }
            QTableCornerButton::section { background: #282a36; }
            QScrollBar:vertical, QScrollBar:horizontal { background: #23272e; width: 12px; border-radius: 6px; }
            QScrollBar::handle { background: #44475a; border-radius: 6px; }
            QScrollBar::add-line, QScrollBar::sub-line { background: none; }
            QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #44475a, stop:1 #282a36); color: #f8f8f2; border-radius: 8px; padding: 8px 20px; font-size: 16px; font-weight: bold; }
            QPushButton:hover { background: #6272a4; color: #f1fa8c; }
            QComboBox { background: #23272e; border: 1px solid #44475a; border-radius: 6px; padding: 4px 8px; color: #8be9fd; font-size: 15px; }
            QComboBox QAbstractItemView { background: #23272e; color: #8be9fd; selection-background-color: #44475a; }
            QTextEdit { background: #181a20; border: 1px solid #44475a; border-radius: 8px; }
            QToolTip { background: #44475a; color: #f8f8f2; border-radius: 6px; font-size: 14px; }
        ''')
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout()
        main_widget.setLayout(layout)

        self.info_label = QLabel("No CCM file loaded")
        self.info_label.setStyleSheet("font-size:20px; font-weight:bold; color:#50fa7b; padding:8px 0 8px 0;")
        layout.addWidget(self.info_label)

        from PyQt5.QtWidgets import QHeaderView
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Code", "Texture ID", "Prespace", "Width", "Advance", "TexRegion Top", "TexRegion Bottom"
        ])
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("selection-background-color:#44475a; selection-color:#f1fa8c; font-size:16px; border-radius:12px; gridline-color:#44475a; border:2px solid #44475a;")
        self.table.horizontalHeader().setStyleSheet("font-size:18px; font-weight:bold; color:#ffb86c; background:#282a36; border-bottom:2px solid #44475a; padding:8px 0;")
        self.table.verticalHeader().setVisible(False)
        self.table.cellChanged.connect(self.update_glyph_from_table)
        self.table.setShowGrid(True)
        self.table.setCornerButtonEnabled(False)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionsClickable(True)
        self.table.horizontalHeader().setHighlightSections(True)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        button_layout = QHBoxLayout()
        for btn_text, slot in [
            ("Load CCM", self.load_ccm),
            ("Add Glyph", self.add_glyph),
            ("Delete Glyph", self.delete_glyph),
            ("Export to Text", self.export_to_text),
            ("Import from Text", self.import_from_text),
            ("Save CCM", self.save_ccm),
            ("Debug Header", self.debug_header),
            ("Dump File", self.dump_file),
            ("Save Dump", self.save_dump)
        ]:
            btn = QPushButton(btn_text)
            btn.setMinimumWidth(120)
            btn.clicked.connect(slot)
            button_layout.addWidget(btn)
        layout.addLayout(button_layout)

        from PyQt5.QtWidgets import QComboBox
        self.texture_selector = QComboBox()
        self.texture_selector.setStyleSheet("font-size:15px; background:#23272e; color:#8be9fd; border-radius:6px; padding:4px 8px;")
        self.texture_selector.currentIndexChanged.connect(self.display_selected_texture)
        layout.addWidget(self.texture_selector)

        self.texture_label = QLabel("No texture loaded")
        self.texture_label.setStyleSheet("font-size:18px; font-weight:bold; color:#bd93f9; background:#23272e; border-radius:10px; padding:12px;")
        self.texture_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.texture_label)

        self.debug_output = QTextEdit()
        self.debug_output.setReadOnly(True)
        self.debug_output.setStyleSheet("font-size:15px; background:#181a20; color:#f8f8f2; border-radius:8px; padding:8px;")
        layout.addWidget(self.debug_output)

        # Footer: code by mofrad
        footer = QLabel("code by mofrad")
        footer.setAlignment(Qt.AlignRight)
        footer.setStyleSheet("color:#44475a; font-size:14px; font-style:italic; padding:6px 12px 0 0;")
        layout.addWidget(footer)

        self.setGeometry(100, 100, 1200, 900)
        self.setWindowTitle("CCM Font Editor - Modern UI")

        self.texture_files = {}  # texture_id: filename

    def display_selected_texture(self):
        idx = self.texture_selector.currentIndex()
        if idx < 0 or not self.texture_files:
            self.texture_label.setText("No texture loaded")
            self.update_table()
            return
        tid = int(self.texture_selector.currentText().split()[0])
        fname = self.texture_files.get(tid)
        if fname:
            try:
                img = Image.open(fname)
                img = img.convert("RGBA")
                qimage = QImage(img.tobytes(), img.width, img.height, QImage.Format_RGBA8888)
                self.texture_label.setPixmap(QPixmap.fromImage(qimage).scaled(200, 200, Qt.KeepAspectRatio))
                self.texture_label.setToolTip(os.path.basename(fname))
            except Exception as e:
                self.texture_label.setText(f"Failed to load: {os.path.basename(fname)}\n{e}")
        else:
            self.texture_label.setText("No texture loaded")
        self.update_table(highlight_texture_id=tid)

    def update_info(self):
        self.info_label.setText(
            f"File: {self.ccm.filename}\n"
            f"Height: {self.ccm.font_height}\n"
            f"Texture Size: {self.ccm.texture_width}x{self.ccm.texture_height}\n"
            f"Num Textures: {self.ccm.texture_count}\n"
            f"Num Glyphs: {self.ccm.glyph_count}"
        )

    def update_table(self, highlight_texture_id=None):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.ccm.glyphs))
        dark_bg = QColor("#23272e")
        alt_bg = QColor("#181a20")
        text_fg = QColor("#f8f8f2")
        for row, glyph in enumerate(self.ccm.glyphs):
            for col, val in enumerate([
                glyph.code, glyph.texture_id, glyph.prespace, glyph.width,
                glyph.advance, (glyph.tex_region.x1, glyph.tex_region.y1),
                (glyph.tex_region.x2, glyph.tex_region.y2)
            ]):
                item = QTableWidgetItem(str(val) if not isinstance(val, tuple) else f"({val[0]}, {val[1]})")
                item.setForeground(text_fg)
                # Alternate row background
                if row % 2 == 0:
                    item.setBackground(dark_bg)
                else:
                    item.setBackground(alt_bg)
                self.table.setItem(row, col, item)
                # Highlight row if matches selected texture
                if highlight_texture_id is not None and glyph.texture_id == highlight_texture_id:
                    item.setBackground(Qt.yellow)
        self.table.resizeColumnsToContents()
        self.table.blockSignals(False)

    def update_glyph_from_table(self, row, column):
        try:
            glyph = self.ccm.glyphs[row]
            value = self.table.item(row, column).text()
            if column == 0:
                glyph.code = int(value)
            elif column == 1:
                texture_id = int(value)
                if texture_id < self.ccm.texture_count:
                    glyph.texture_id = texture_id
                else:
                    logger.warning(f"Invalid texture_id {value} for row {row}")
                    self.table.setItem(row, column, QTableWidgetItem(str(glyph.texture_id)))
                    QMessageBox.warning(self, "Warning", f"Texture ID must be less than {self.ccm.texture_count}")
            elif column == 2:
                glyph.prespace = int(value)
            elif column == 3:
                glyph.width = int(value)
            elif column == 4:
                glyph.advance = int(value)
            elif column == 5:
                x1, y1 = eval(value)
                glyph.tex_region.x1 = x1
                glyph.tex_region.y1 = y1
            elif column == 6:
                x2, y2 = eval(value)
                glyph.tex_region.x2 = x2
                glyph.tex_region.y2 = y2
            logger.debug(f"Updated glyph {row} column {column} to {value}")
        except Exception as e:
            error_msg = f"Failed to update glyph {row} column {column}: {str(e)}"
            logger.error(error_msg)
            self.update_table()
            QMessageBox.critical(self, "Error", error_msg)

    def load_ccm(self):
        import glob
        file_path, _ = QFileDialog.getOpenFileName(self, "Open CCM File", "", "CCM Files (*.ccm)")
        if file_path:
            success, message = self.ccm.load_file(file_path)
            if success:
                self.update_info()
                self.update_table()
                base = os.path.splitext(file_path)[0]
                texture_files = {}
                for ext in ['.png', '.dds']:
                    for i in range(self.ccm.texture_count):
                        for pattern in [f"{base}_{i}{ext}", f"{base}_{i:04d}{ext}"]:
                            if os.path.exists(pattern):
                                texture_files[i] = pattern
                    if os.path.exists(base + ext):
                        texture_files[0] = base + ext

                self.texture_files = texture_files
                self.texture_selector.clear()
                if texture_files:
                    for tid in sorted(texture_files):
                        self.texture_selector.addItem(f"{tid} - {os.path.basename(texture_files[tid])}")
                    self.texture_selector.setCurrentIndex(0)
                    self.display_selected_texture()
                else:
                    self.texture_label.setText("No texture found (.png or .dds)")
                QMessageBox.information(self, "Success", "CCM file loaded successfully")
            else:
                self.debug_output.setText(f"Load failed: {message}")
                QMessageBox.critical(self, "Error", f"Failed to load CCM file: {message}")

    def add_glyph(self):
        code, ok = QInputDialog.getInt(self, "Add Glyph", "Unicode Code (decimal):")
        if not ok:
            return
        texture_id, ok = QInputDialog.getInt(self, "Add Glyph", f"Texture ID (0-{self.ccm.texture_count-1}):")
        if not ok or texture_id >= self.ccm.texture_count:
            QMessageBox.critical(self, "Error", f"Invalid Texture ID, must be 0-{self.ccm.texture_count-1}")
            return
        prespace, ok = QInputDialog.getInt(self, "Add Glyph", "Prespace:")
        if not ok:
            return
        width, ok = QInputDialog.getInt(self, "Add Glyph", "Width:")
        if not ok:
            return
        advance, ok = QInputDialog.getInt(self, "Add Glyph", "Advance:")
        if not ok:
            return
        x1, ok = QInputDialog.getInt(self, "Add Glyph", "TexRegion x1:")
        if not ok:
            return
        y1, ok = QInputDialog.getInt(self, "Add Glyph", "TexRegion y1:")
        if not ok:
            return
        x2, ok = QInputDialog.getInt(self, "Add Glyph", "TexRegion x2:")
        if not ok:
            return
        y2, ok = QInputDialog.getInt(self, "Add Glyph", "TexRegion y2:")
        if not ok:
            return

        tex_region = TexRegion(x1, y1, x2, y2)
        glyph = Glyph(code, len(self.ccm.glyphs), texture_id, prespace, width, advance, tex_region)
        self.ccm.glyphs.append(glyph)
        self.ccm.glyph_count = len(self.ccm.glyphs)
        self.ccm.tex_region_count = len(self.ccm.glyphs)
        self.update_table()
        logger.info(f"Added new glyph: code={code}, texture_id={texture_id}")

    def delete_glyph(self):
        row = self.table.currentRow()
        if row >= 0:
            glyph = self.ccm.glyphs.pop(row)
            self.ccm.glyph_count = len(self.ccm.glyphs)
            self.ccm.tex_region_count = len(self.ccm.glyphs)
            self.update_table()
            logger.info(f"Deleted glyph at row {row}: code={glyph.code}")
        else:
            QMessageBox.warning(self, "Warning", "Select a glyph to delete")

    def export_to_text(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export to Text", "", "Text Files (*.txt)")
        if file_path:
            success, message = self.ccm.export_to_text(file_path)
            if success:
                QMessageBox.information(self, "Success", "Exported to text successfully")
            else:
                self.debug_output.setText(f"Export failed: {message}")
                QMessageBox.critical(self, "Error", message)

    def import_from_text(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Import from Text", "", "Text Files (*.txt)")
        if file_path:
            success, message = self.ccm.import_from_text(file_path)
            if success:
                self.update_info()
                self.update_table()
                QMessageBox.information(self, "Success", "Imported from text successfully")
            else:
                self.debug_output.setText(f"Import failed: {message}")
                QMessageBox.critical(self, "Error", message)

    def save_ccm(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Save CCM File", "", "CCM Files (*.ccm)")
        if file_path:
            success, message = self.ccm.save_file(file_path)
            if success:
                self.ccm.filename = file_path
                self.update_info()
                QMessageBox.information(self, "Success", "Saved CCM file successfully")
            else:
                self.debug_output.setText(f"Save failed: {message}")
                QMessageBox.critical(self, "Error", message)

    def debug_header(self):
        if not self.ccm.filename:
            QMessageBox.warning(self, "Warning", "No CCM file loaded")
            return
        try:
            header_size = min(len(self.ccm.raw_data), 28)
            debug_info = f"Raw header (hex): {binascii.hexlify(self.ccm.raw_data[:header_size]).decode()}\n"
            debug_info += f"Format: {hex(self.ccm.format)}\n"
            debug_info += f"File Size: {self.ccm.file_size}\n"
            debug_info += f"Font Height: {self.ccm.font_height}\n"
            debug_info += f"Texture Size: {self.ccm.texture_width}x{self.ccm.texture_height}\n"
            debug_info += f"TexRegion Count: {self.ccm.tex_region_count}\n"
            debug_info += f"Glyph Count: {self.ccm.glyph_count}\n"
            debug_info += f"TexRegion Offset: {self.ccm.tex_region_offset}\n"
            debug_info += f"Glyph Offset: {self.ccm.glyph_offset}\n"
            debug_info += f"Alignment: {self.ccm.alignment}\n"
            debug_info += f"Texture Count: {self.ccm.texture_count}"
            self.debug_output.setText(debug_info)
            logger.debug(f"Displayed debug header: {debug_info}")
        except Exception as e:
            error_msg = f"Failed to debug header: {str(e)}"
            logger.error(error_msg)
            self.debug_output.setText(error_msg)
            QMessageBox.critical(self, "Error", error_msg)

    def dump_file(self):
        success, dump = self.ccm.dump_file()
        if success:
            self.debug_output.setText(dump)
            logger.info("Dumped file content to debug output")
        else:
            self.debug_output.setText(dump)
            QMessageBox.critical(self, "Error", dump)

    def save_dump(self):
        if not self.ccm.filename:
            QMessageBox.warning(self, "Warning", "No CCM file loaded")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Dump", "", "Text Files (*.txt)")
        if file_path:
            success, dump = self.ccm.dump_file()
            if success:
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(dump)
                    logger.info(f"Saved dump to: {file_path}")
                    QMessageBox.information(self, "Success", "Dump saved successfully")
                except Exception as e:
                    error_msg = f"Failed to save dump: {str(e)}"
                    logger.error(error_msg)
                    self.debug_output.setText(error_msg)
                    QMessageBox.critical(self, "Error", error_msg)
            else:
                self.debug_output.setText(dump)
                QMessageBox.critical(self, "Error", dump)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    editor = CCMEditor()
    editor.show()
    sys.exit(app.exec_())
