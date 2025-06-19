# XV2AutoShader
Automated Dragon Ball Xenoverse 2 shader setup for Blender 4.0+
Applies a heavily modified version of Starr's Xenoverse 2 camera-based shaders and handles texture assignment automatically. No template files needed.
Features
Automatic Shader Setup

Applies XV2 shaders to all materials with one click
Finds and assigns textures automatically (000, 001, 002, DYT files)
Supports MSK, XVM, TOON_UNIF_ENV, and Eye shader types
Reads EMM XML files for MatScale1X values and shader detection

Shader Types

MSK: Ambient occlusion using blue channel (mask gets inverted automatically)
XVM: Color overlay using red channel for costume variants
TOON_UNIF_ENV: Glass/transparent materials with camera reflections
Eye: Specialized eye shaders with automatic channel optimization

DYT Transformations

Switch between original DYT and DATA_001/002/003 files
Real-time costume variant preview
Automatically detects DATA files in texture folders

Material Utilities

Copy/paste DYT settings between materials
Fix black materials by disconnecting EMB Alpha
Repair corrupted DXT1 DDS files
Works on selected objects

Setup

Install addon in Blender 4.0+
Open 3D Viewport → Sidebar (N) → XV2 tab
Set EMM Folder to your extracted EMM XML files
Set Texture Folder to your DDS/PNG texture root

Usage
Apply Shaders:

Import XV2 model
Click "Apply/Update Shaders"

DYT Transformations:

Select objects
Use DYT Transformation panel to switch costume variants

Material Tools:

Copy DYT: Select source → "Copy DYT"
Paste DYT: Select targets → "Paste DYT"
Fix black materials: Select objects → "Disconnect EMB Alpha"

File Structure
Textures/
├── char_000.dds    # Lines
├── char_001.dds    # Mask (MSK/XVM)
├── char_dyt.dds    # Lighting
├── DATA_001.dds    # Variant 1
└── DATA_002.dds    # Variant 2

EMM/
└── char.emm.xml    # Material definitions
Credits

Shader: Starr

Quick Tutorial
First Time Setup

Install addon in Blender 4.0+
Press N to open sidebar → go to XV2 tab
Set EMM Folder to your extracted EMM XML files
Set Texture Folder to your DDS/PNG texture root folder

Basic Workflow

Import your XV2 model (FBX, DAE, etc.)
Click "Apply/Update Shaders" - that's it!

All materials get XV2 shaders
Textures are found and assigned automatically
MSK/XVM/Eye shaders are detected from EMM files



Advanced Features
Switch Costume Variants:

Select character → DYT Transformation panel → click DATA_001, DATA_002, etc.

Copy Shaders Between meshes:

Select source character → "Copy DYT"
Select target characters → "Paste DYT"

Fix Black Materials (Some SCDs):

Select affected objects → "Disconnect EMB Alpha"
