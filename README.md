# XV2 Auto-Shader

**Automated Dragon Ball Xenoverse 2 shader setup for Blender 4.0+**

Applies a heavily modified version of TempestStarr's Xenoverse 2 camera-based shaders and handles texture assignment automatically. No template files needed.

## Features

### Automatic Shader Setup
- Applies XV2 shaders to all materials with one click
- Finds and assigns textures automatically (000, 001, 002, DYT files)
- Supports MSK, XVM, TOON_UNIF_ENV, and Eye shader types
- Reads EMM XML files for MatScale1X values and shader detection

### Shader Types
- **MSK**: Ambient occlusion using blue channel (mask gets inverted automatically)
- **XVM**: Color overlay using red channel for costume variants
- **TOON_UNIF_ENV**: Glass/transparent materials with camera reflections
- **Eye**: Specialized eye shaders with automatic channel optimization

### DYT Transformations
- Switch between original DYT and DATA_001/002/003 files
- Real-time costume variant preview
- Automatically detects DATA files in texture folders

### Material Utilities
- Copy/paste DYT settings between materials
- Fix black materials by disconnecting EMB Alpha
- Repair corrupted DXT1 DDS files
- Works on selected objects

## Quick Tutorial

### First Time Setup
1. Install addon in Blender 4.0+
2. Press `N` to open sidebar → go to **XV2** tab
3. Set **EMM Folder** to your extracted EMM XML files
4. Set **Texture Folder** to your DDS texture root folder

### Basic Workflow
1. **Import your XV2 model** (FBX)
2. **Click "Apply/Update Shaders"** - that's it!
   - All materials get XV2 shaders
   - Textures are found and assigned automatically
   - MSK/XVM/Eye shaders are detected from EMM files

### Advanced Features

**Switch Costume Variants:**
- Select character → DYT Transformation panel → click DATA_001, DATA_002, etc.

**Copy Shaders Between Characters:**
- Select source character → "Copy DYT" 
- Select target characters → "Paste DYT"

**Fix Black Materials:**
- Select affected objects → "Disconnect EMB Alpha"

## File Structure
```
Textures/
├── char_000.dds    # Lines
├── char_001.dds    # Mask (MSK/XVM)
├── char_dyt.dds    # Lighting
├── DATA_001.dds    # Variant 1
└── DATA_002.dds    # Variant 2

EMM/
└── char.emm.xml    # Material definitions
```

## Credits
- **Shader**: TempestStarr - https://linktr.ee/TempestStarr
- **Addon**: Imxiater
-Ko-fi in case I post an update here: https://ko-fi.com/imxiater
