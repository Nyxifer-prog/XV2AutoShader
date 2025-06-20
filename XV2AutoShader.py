bl_info = {
    "name": "XV2 Auto-Shader (Standalone)",
    "author": "Imxiater",
    "version": (4, 5, 0),  
    "blender": (4, 2, 0),
    "category": "Material",
    "description": (
        "Applies Starr's Xenoverse 2 camera-based shader. "
        "Replaces existing materials with clean node-based versions, "
        "cleans up unused original materials. Supports TOON_UNIF_ENV (glass), "
        "MSK (Ambient Occlusion via Blue Channel of mask), and XVM Dual EMB (Color Overlay via Red Channel of mask) "
        "shader variants. 100% standalone – no template .blend required."
    ),
}

import bpy
import os
import re
import xml.etree.ElementTree as ET
from bpy.props import StringProperty, EnumProperty, BoolProperty
from bpy.types import AddonPreferences, Panel, Operator
import struct
import tempfile
import mathutils
_copied_dyt_image = None
_copied_dyt_line = None


# --- NODE GROUP DEFINITIONS ---


def scan_and_store_dyt_data_files(mat, dyt_image):
    """Scan for DATA_001.dds, DATA_002.dds etc. in the DYT image's folder and store results"""
    print(f"[XV2 DATA DEBUG] Starting DATA scan for material: {mat.name}")
    print(f"[XV2 DATA DEBUG] DYT image name: {dyt_image.name if dyt_image else 'None'}")

    if not mat or not dyt_image:
        print(f"[XV2 DATA DEBUG] ABORT: Missing mat or dyt_image")
        return

    # Method 1: Try image filepath
    dyt_path = None
    if dyt_image.filepath:
        raw_path = dyt_image.filepath
        abs_path = bpy.path.abspath(dyt_image.filepath)
        print(f"[XV2 DATA DEBUG] DYT image filepath (raw): '{raw_path}'")
        print(f"[XV2 DATA DEBUG] DYT image filepath (absolute): '{abs_path}'")
        print(f"[XV2 DATA DEBUG] Path exists: {os.path.exists(abs_path)}")

        if os.path.exists(abs_path):
            dyt_path = abs_path
            print(f"[XV2 DATA DEBUG] ✓ Using DYT path from image filepath: {dyt_path}")
        else:
            print(f"[XV2 DATA DEBUG] ✗ DYT filepath doesn't exist on disk")
    else:
        print(f"[XV2 DATA DEBUG] ✗ DYT image has no filepath")

    if not dyt_path:
        print(f"[XV2 DATA DEBUG] ✗ Could not locate DYT file for '{mat.name}' - DATA scanning skipped")
        return

    # Now scan for DATA files in the same folder
    dyt_folder = os.path.dirname(dyt_path)
    print(f"[XV2 DATA DEBUG] DYT folder: {dyt_folder}")
    print(f"[XV2 DATA DEBUG] Folder exists: {os.path.isdir(dyt_folder)}")

    if not os.path.isdir(dyt_folder):
        print(f"[XV2 DATA DEBUG] ✗ DYT folder is not a directory")
        return

    # List all files in the DYT folder for debugging
    try:
        all_files = os.listdir(dyt_folder)
        print(f"[XV2 DATA DEBUG] All files in DYT folder ({len(all_files)}): {all_files}")

        # Filter to just .dds files
        dds_files = [f for f in all_files if f.lower().endswith('.dds')]
        print(f"[XV2 DATA DEBUG] DDS files in folder: {dds_files}")

        # Filter to DATA_xxx.dds files (try both naming patterns)
        data_files_underscore = [f for f in dds_files if f.upper().startswith('DATA_')]
        data_files_no_underscore = [f for f in dds_files if
                                    f.upper().startswith('DATA') and not f.upper().startswith('DATA_')]
        print(f"[XV2 DATA DEBUG] DATA_xxx.dds files found: {data_files_underscore}")
        print(f"[XV2 DATA DEBUG] DATAxxx.dds files found: {data_files_no_underscore}")
    except Exception as e:
        print(f"[XV2 DATA DEBUG] Error listing files: {e}")

    # Store original DYT path
    mat["xv2_original_dyt_path"] = dyt_path

    # Scan for DATA files - try both naming patterns
    available_data_files = []
    data_index = 1

    print(f"[XV2 DATA DEBUG] Starting sequential DATA file scan...")
    while True:
        # Try pattern 1: DATA_001.dds (with underscore)
        data_filename_1 = f"DATA_{str(data_index).zfill(3)}.dds"
        data_path_1 = os.path.join(dyt_folder, data_filename_1)

        # Try pattern 2: DATA001.dds (no underscore)
        data_filename_2 = f"DATA{str(data_index).zfill(3)}.dds"
        data_path_2 = os.path.join(dyt_folder, data_filename_2)

        print(f"[XV2 DATA DEBUG] Checking for patterns:")
        print(f"  Pattern 1: {data_filename_1} exists: {os.path.exists(data_path_1)}")
        print(f"  Pattern 2: {data_filename_2} exists: {os.path.exists(data_path_2)}")

        if os.path.exists(data_path_1):
            available_data_files.append(data_path_1)
            print(f"[XV2 DATA DEBUG] ✓ Found DATA file #{data_index}: {data_filename_1}")
            data_index += 1
        elif os.path.exists(data_path_2):
            available_data_files.append(data_path_2)
            print(f"[XV2 DATA DEBUG] ✓ Found DATA file #{data_index}: {data_filename_2}")
            data_index += 1
        else:
            print(f"[XV2 DATA DEBUG] ✗ DATA file #{data_index} not found in either pattern, stopping scan")
            break  # Stop when we don't find the next sequential DATA file

    # Store available DATA files
    mat["xv2_data_files_count"] = len(available_data_files)
    for i, data_path in enumerate(available_data_files):
        mat[f"xv2_data_file_{i + 1}"] = data_path

    print(f"[XV2 DATA DEBUG] FINAL RESULT: {len(available_data_files)} DATA files stored in material")

    if available_data_files:
        print(
            f"[XV2 Transform] Found {len(available_data_files)} DATA files for '{mat.name}': DATA_001 to DATA_{str(len(available_data_files)).zfill(3)}")
    else:
        print(f"[XV2 Transform] No DATA files found in {dyt_folder}")
def get_selected_objects_max_data_count(context):
    """Get the maximum DATA file count across all selected objects' materials"""
    max_count = 0

    for obj in context.selected_objects:
        if obj.type != 'MESH' or not obj.material_slots:
            continue

        for slot in obj.material_slots:
            if not slot.material:
                continue

            mat = slot.material
            data_count = mat.get("xv2_data_files_count", 0)
            max_count = max(max_count, data_count)

    return max_count


def apply_dyt_transformation(context, transform_index):
    """Apply DYT transformation to selected objects"""
    if not context.selected_objects:
        return 0

    materials_updated = 0

    for obj in context.selected_objects:
        if obj.type != 'MESH' or not obj.material_slots:
            continue

        for slot in obj.material_slots:
            if not slot.material:
                continue

            mat = slot.material
            dyt_node = mat.node_tree.nodes.get("Image Texture.004") if mat.use_nodes and mat.node_tree else None

            if not dyt_node or dyt_node.type != 'TEX_IMAGE':
                continue

            if transform_index == 0:
                # Return to original DYT
                original_path = mat.get("xv2_original_dyt_path")
                if original_path and os.path.exists(original_path):
                    try:
                        original_image = bpy.data.images.load(original_path, check_existing=True)
                        dyt_node.image = original_image
                        materials_updated += 1
                    except RuntimeError as e:
                        print(f"[XV2 Transform] Warning: Could not load original DYT: {original_path} - {e}")

            else:
                # Apply DATA file
                data_count = mat.get("xv2_data_files_count", 0)
                if transform_index <= data_count:
                    data_path = mat.get(f"xv2_data_file_{transform_index}")
                    if data_path and os.path.exists(data_path):
                        try:
                            data_image = bpy.data.images.load(data_path, check_existing=True)
                            dyt_node.image = data_image
                            materials_updated += 1
                        except RuntimeError as e:
                            print(f"[XV2 Transform] Warning: Could not load DATA file: {data_path} - {e}")

    return materials_updated


class XV2_OT_set_dyt_transformation(Operator):
    bl_idname = "xv2.set_dyt_transformation"
    bl_label = "Set DYT Transformation"
    bl_description = "Switch DYT textures between original and DATA transformation files"
    bl_options = {'REGISTER', 'UNDO'}

    transform_index: bpy.props.IntProperty(
        name="Transform Index",
        description="0=Original, 1=DATA_001, 2=DATA_002, etc.",
        default=0,
        min=0
    )

    def execute(self, context):
        if not context.selected_objects:
            self.report({'WARNING'}, "No objects selected.")
            return {'CANCELLED'}

        materials_updated = apply_dyt_transformation(context, self.transform_index)

        if materials_updated > 0:
            transform_name = "Original" if self.transform_index == 0 else f"DATA_{str(self.transform_index).zfill(3)}"
            self.report({'INFO'}, f"Applied {transform_name} DYT to {materials_updated} materials.")
        else:
            self.report({'WARNING'}, "No applicable materials found or DYT files missing.")

        return {'FINISHED'}


class XV2_PT_transformation_panel(Panel):
    bl_label = "DYT Transformation"
    bl_idname = "XV2_PT_TRANSFORMATION"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'XV2'

    def draw(self, context):
        layout = self.layout

        # Check if any objects are selected
        if not context.selected_objects:
            layout.label(text="Select objects to use DYT Transform", icon='INFO')
            return

        # Get max DATA count from selected objects
        max_data_count = get_selected_objects_max_data_count(context)

        if max_data_count == 0:
            layout.label(text="No transformation DATA files found", icon='INFO')
            layout.label(text="(No DATA_001.dds, DATA_002.dds etc.)")
            return

        box = layout.box()
        col = box.column(align=True)
        col.label(text=f"DYT Transform (0-{max_data_count}):", icon='FILE_IMAGE')

        # Create buttons for each transformation
        row = col.row(align=True)

        # Original (0)
        op = row.operator("xv2.set_dyt_transformation", text="Original")
        op.transform_index = 0

        # DATA files (1, 2, 3, etc.)
        for i in range(1, max_data_count + 1):
            if i > 1 and (i - 1) % 4 == 0:  # New row every 4 buttons
                row = col.row(align=True)

            op = row.operator("xv2.set_dyt_transformation", text=f"DATA_{str(i).zfill(3)}")
            op.transform_index = i


# MODIFICATION to existing assign_images function:
# Add this call at the end of assign_images function, after DYT assignment:

def assign_images_enhanced_with_data_scan(mat, primary_stub, original_material_name, tex_root, shader_type="",
                                          mat_scale1x_val=None):
    """Enhanced version that includes DATA file scanning"""
    # Call existing function
    if is_eye_shader(shader_type):
        assign_eye_textures(mat, primary_stub, original_material_name, tex_root)
    else:
        assign_images(mat, primary_stub, original_material_name, tex_root, shader_type, mat_scale1x_val)

    # After assignment, scan for DATA files if DYT was assigned
    if mat and mat.use_nodes and mat.node_tree:
        dyt_node = mat.node_tree.nodes.get("Image Texture.004")
        if dyt_node and dyt_node.image:
            scan_and_store_dyt_data_files(mat, dyt_node.image)


def xenoverse___dimps_001_node_group_def():
    """Remove MSK redundancy - MSK now just inverts mask and uses XVM system"""

    if "Xenoverse - Dimps.001" in bpy.data.node_groups:
        # Check if it has the old MSK sockets, if so, remove and recreate
        group_to_check = bpy.data.node_groups["Xenoverse - Dimps.001"]
        has_msk_strength = any(s.name == "MSK Strength" for s in group_to_check.interface.items_tree if
                               s.item_type == 'SOCKET' and s.in_out == 'INPUT')
        has_is_msk = any(s.name == "Is MSK" for s in group_to_check.interface.items_tree if
                         s.item_type == 'SOCKET' and s.in_out == 'INPUT')
        if has_msk_strength or has_is_msk:
            print("[XV2 DEBUG] 'Xenoverse - Dimps.001' node group has old MSK logic. Removing and recreating.")
            bpy.data.node_groups.remove(group_to_check)
        else:
            print("[XV2 DEBUG] Found existing 'Xenoverse - Dimps.001' node group (assumed up-to-date).")
            return group_to_check

    xenoverse___dimps_001 = bpy.data.node_groups.new(type='ShaderNodeTree', name="Xenoverse - Dimps.001")
    print("[XV2 DEBUG] Creating new 'Xenoverse - Dimps.001' node group (MSK = inverted XVM).")

    # Interface Sockets - REMOVED MSK Strength and Is MSK sockets only
    xenoverse___dimps_001.interface.new_socket(name="Result", in_out='OUTPUT', socket_type='NodeSocketShader')
    s = xenoverse___dimps_001.interface.new_socket(name="EMB Color", in_out='INPUT', socket_type='NodeSocketColor')
    s.default_value = (0.8, 0.8, 0.8, 1.0)
    s = xenoverse___dimps_001.interface.new_socket(name="EMB Alpha", in_out='INPUT', socket_type='NodeSocketColor')
    s.default_value = (0.0, 0.0, 0.0, 1.0)
    s = xenoverse___dimps_001.interface.new_socket(name="DYT", in_out='INPUT', socket_type='NodeSocketColor')
    s.default_value = (0.5, 0.5, 0.5, 1.0)
    s = xenoverse___dimps_001.interface.new_socket(name="Transparency", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.0
    s = xenoverse___dimps_001.interface.new_socket(name="DYT Color Override", in_out='INPUT',
                                                   socket_type='NodeSocketFloat')
    s.default_value = 0.0
    s = xenoverse___dimps_001.interface.new_socket(name="DYT Color", in_out='INPUT', socket_type='NodeSocketColor')
    s.default_value = (0.5, 0.0012233, 0.072981, 1.0)
    s = xenoverse___dimps_001.interface.new_socket(name="DYT Hue", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.5
    s = xenoverse___dimps_001.interface.new_socket(name="DYT Saturation", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 1.0
    s = xenoverse___dimps_001.interface.new_socket(name="DYT Value", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 1.0
    s = xenoverse___dimps_001.interface.new_socket(name="EMB Line Thickness", in_out='INPUT',
                                                   socket_type='NodeSocketFloat')
    s.default_value = 0.5
    s = xenoverse___dimps_001.interface.new_socket(name="EMB Blood", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.0
    s = xenoverse___dimps_001.interface.new_socket(name="Blood Color", in_out='INPUT', socket_type='NodeSocketColor')
    s.default_value = (1.0, 0.034956, 0.26177, 1.0)
    s = xenoverse___dimps_001.interface.new_socket(name="EMB Scratch", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.0
    s = xenoverse___dimps_001.interface.new_socket(name="Dual EMB Mask", in_out='INPUT', socket_type='NodeSocketColor')
    s.default_value = (0.0, 0.0, 0.0, 1.0)
    s = xenoverse___dimps_001.interface.new_socket(name="Dual EMB Strength", in_out='INPUT',
                                                   socket_type='NodeSocketFloat')
    s.default_value = 1.0
    s = xenoverse___dimps_001.interface.new_socket(name="Dual EMB Color", in_out='INPUT', socket_type='NodeSocketColor')
    s.default_value = (0.5, 0.5, 0.5, 1.0)
    s = xenoverse___dimps_001.interface.new_socket(name="Is TOON_UNIF_ENV", in_out='INPUT',
                                                   socket_type='NodeSocketFloat')
    s.default_value = 0.0
    # ONLY XVM socket remains - no more MSK sockets
    s = xenoverse___dimps_001.interface.new_socket(name="Is XVM", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.0

    # Node positioning
    X_OFFSET = 250
    Y_OFFSET = 150

    group_input = xenoverse___dimps_001.nodes.new("NodeGroupInput")
    group_input.name = "Group Input"
    group_input.location = (-1400, 0)
    group_output = xenoverse___dimps_001.nodes.new("NodeGroupOutput")
    group_output.name = "Group Output"
    group_output.is_active_output = True
    group_output.location = (1700, 0)

    # EMB Processing Path (UNCHANGED)
    separate_rgb_001 = xenoverse___dimps_001.nodes.new("ShaderNodeSeparateColor")
    separate_rgb_001.name = "Separate RGB.001"
    separate_rgb_001.location = (-1100, 200)
    math_005 = xenoverse___dimps_001.nodes.new("ShaderNodeMath")
    math_005.name = "Math.005"
    math_005.operation = 'MULTIPLY'
    math_005.location = (-800, 350)
    invert_004 = xenoverse___dimps_001.nodes.new("ShaderNodeInvert")
    invert_004.name = "Invert.004"
    invert_004.inputs[0].default_value = 1.0
    invert_004.location = (-550, 350)
    math_002_node = xenoverse___dimps_001.nodes.new("ShaderNodeMath")
    math_002_node.name = "Math.002"
    math_002_node.operation = 'MULTIPLY'
    math_002_node.location = (-800, 150)
    mix_012 = xenoverse___dimps_001.nodes.new("ShaderNodeMix")
    mix_012.name = "Mix.012"
    mix_012.blend_type = 'MULTIPLY'
    mix_012.data_type = 'RGBA'
    mix_012.inputs[0].default_value = 1.0
    mix_012.location = (-550, 150)
    mix_011 = xenoverse___dimps_001.nodes.new("ShaderNodeMix")
    mix_011.name = "Mix.011"
    mix_011.blend_type = 'MULTIPLY'
    mix_011.data_type = 'RGBA'
    mix_011.location = (-550, 50)
    mix_010 = xenoverse___dimps_001.nodes.new("ShaderNodeMix")
    mix_010.name = "Mix.010"
    mix_010.blend_type = 'ADD'
    mix_010.data_type = 'RGBA'
    mix_010.inputs[0].default_value = 1.0
    mix_010.location = (-300, 100)

    invert = xenoverse___dimps_001.nodes.new("ShaderNodeInvert")
    invert.name = "Invert"
    invert.inputs[0].default_value = 1.0
    invert.location = (-1100, -100)
    math = xenoverse___dimps_001.nodes.new("ShaderNodeMath")
    math.name = "Math"
    math.operation = 'GREATER_THAN'
    math.location = (-800, -100)

    # XVM/DYT Color Override Path (UNCHANGED from your working version)
    dual_emb_dyt_override_frame = xenoverse___dimps_001.nodes.new("NodeFrame")
    dual_emb_dyt_override_frame.name = "Dual EMB DYT Override Frame"
    dual_emb_dyt_override_frame.label = "DYT Color Override (XVM Red Channel)"
    dual_emb_dyt_override_frame.location = (-975, -300)
    dual_emb_dyt_override_frame.width = 550

    separate_dual_emb_mask_for_dyt_override = xenoverse___dimps_001.nodes.new("ShaderNodeSeparateColor")
    separate_dual_emb_mask_for_dyt_override.name = "Separate Mask for DYT Override"
    separate_dual_emb_mask_for_dyt_override.location = (-1100, -300)
    separate_dual_emb_mask_for_dyt_override.parent = dual_emb_dyt_override_frame

    xvm_strength_multiply = xenoverse___dimps_001.nodes.new("ShaderNodeMath")
    xvm_strength_multiply.name = "XVM Strength Multiply"
    xvm_strength_multiply.operation = 'MULTIPLY'
    xvm_strength_multiply.location = (-900, -250)
    xvm_strength_multiply.parent = dual_emb_dyt_override_frame

    xvm_enable_multiply = xenoverse___dimps_001.nodes.new("ShaderNodeMath")
    xvm_enable_multiply.name = "XVM Enable Multiply"
    xvm_enable_multiply.operation = 'MULTIPLY'
    xvm_enable_multiply.location = (-750, -250)
    xvm_enable_multiply.parent = dual_emb_dyt_override_frame

    dyt_override_color_selector = xenoverse___dimps_001.nodes.new("ShaderNodeMix")
    dyt_override_color_selector.name = "DYT Override Color Selector"
    dyt_override_color_selector.blend_type = 'MIX'
    dyt_override_color_selector.data_type = 'RGBA'
    dyt_override_color_selector.location = (-600, -300)
    dyt_override_color_selector.parent = dual_emb_dyt_override_frame

    # DYT Color Processing Path (UNCHANGED)
    frame_dyt_processing = xenoverse___dimps_001.nodes.new("NodeFrame")
    frame_dyt_processing.name = "Frame DYT Processing"
    frame_dyt_processing.label_size = 20
    frame_dyt_processing.shrink = True
    frame_dyt_processing.location = (-425, -300)
    frame_dyt_processing.width = 500
    frame_dyt_processing.label = "DYT Color Processing"
    mix_dyt_color_override_apply = xenoverse___dimps_001.nodes.new("ShaderNodeMix")
    mix_dyt_color_override_apply.name = "Mix DYT Color Override Apply"
    mix_dyt_color_override_apply.blend_type = 'MULTIPLY'
    mix_dyt_color_override_apply.data_type = 'RGBA'
    mix_dyt_color_override_apply.location = (-550, -300)
    mix_dyt_color_override_apply.parent = frame_dyt_processing
    hue_saturation_value = xenoverse___dimps_001.nodes.new("ShaderNodeHueSaturation")
    hue_saturation_value.name = "Hue/Saturation/Value"
    hue_saturation_value.inputs[3].default_value = 1.0
    hue_saturation_value.location = (-300, -300)
    hue_saturation_value.parent = frame_dyt_processing

    # Combine DYT + Lines (UNCHANGED)
    mix_002 = xenoverse___dimps_001.nodes.new("ShaderNodeMix")
    mix_002.name = "Mix.002"
    mix_002.blend_type = 'MULTIPLY'
    mix_002.data_type = 'RGBA'
    mix_002.inputs[0].default_value = 1.0
    mix_002.location = (0, -150)

    # Apply Scratches & Blood (UNCHANGED)
    mix_016 = xenoverse___dimps_001.nodes.new("ShaderNodeMix")
    mix_016.name = "Mix.016"
    mix_016.blend_type = 'MULTIPLY'
    mix_016.data_type = 'RGBA'
    mix_016.location = (0, 200)

    # TOON_UNIF_ENV Path (UNCHANGED)
    camera_fresnel_node = xenoverse___dimps_001.nodes.new("ShaderNodeFresnel")
    camera_fresnel_node.name = "Camera Fresnel"
    camera_fresnel_node.inputs[0].default_value = 1.45
    camera_fresnel_node.location = (-800, -900)
    fresnel_power = xenoverse___dimps_001.nodes.new("ShaderNodeMath")
    fresnel_power.name = "Fresnel Power"
    fresnel_power.operation = 'POWER'
    fresnel_power.inputs[1].default_value = 2.0
    fresnel_power.location = (-550, -900)
    fresnel_factor = xenoverse___dimps_001.nodes.new("ShaderNodeMath")
    fresnel_factor.name = "Fresnel Factor"
    fresnel_factor.operation = 'MULTIPLY'
    fresnel_factor.inputs[1].default_value = 0.15
    fresnel_factor.location = (-300, -900)

    toon_env_depth = xenoverse___dimps_001.nodes.new("ShaderNodeMix")
    toon_env_depth.name = "TOON ENV Depth"
    toon_env_depth.blend_type = 'MULTIPLY'
    toon_env_depth.data_type = 'RGBA'
    toon_env_depth.inputs[0].default_value = 0.7
    toon_env_depth.location = (700, 150)
    highlight_add = xenoverse___dimps_001.nodes.new("ShaderNodeMix")
    highlight_add.name = "Glass Highlights"
    highlight_add.blend_type = 'SCREEN'
    highlight_add.data_type = 'RGBA'
    highlight_add.location = (700, -50)
    toon_env_final_mix = xenoverse___dimps_001.nodes.new("ShaderNodeMix")
    toon_env_final_mix.name = "TOON ENV Final Mix"
    toon_env_final_mix.blend_type = 'MIX'
    toon_env_final_mix.data_type = 'RGBA'
    toon_env_final_mix.location = (1000, 0)

    # Final Output (UNCHANGED)
    transparent_bsdf = xenoverse___dimps_001.nodes.new("ShaderNodeBsdfTransparent")
    transparent_bsdf.name = "Transparent BSDF"
    transparent_bsdf.location = (1250, -200)
    mix_shader = xenoverse___dimps_001.nodes.new("ShaderNodeMixShader")
    mix_shader.name = "Mix Shader"
    mix_shader.location = (1450, 0)

    # LINKS - Remove all MSK-specific links, keep everything else the same

    # EMB Processing Path Links (UNCHANGED)
    xenoverse___dimps_001.links.new(group_input.outputs["EMB Color"], separate_rgb_001.inputs[0])
    xenoverse___dimps_001.links.new(separate_rgb_001.outputs[0], math_005.inputs[0])
    xenoverse___dimps_001.links.new(group_input.outputs["EMB Scratch"], math_005.inputs[1])
    xenoverse___dimps_001.links.new(math_005.outputs[0], invert_004.inputs[1])
    xenoverse___dimps_001.links.new(math_005.outputs[0], mix_016.inputs[0])

    xenoverse___dimps_001.links.new(separate_rgb_001.outputs[1], math_002_node.inputs[0])
    xenoverse___dimps_001.links.new(group_input.outputs["EMB Blood"], math_002_node.inputs[1])
    xenoverse___dimps_001.links.new(math_002_node.outputs[0], mix_012.inputs[6])
    xenoverse___dimps_001.links.new(math_002_node.outputs[0], mix_011.inputs[0])
    xenoverse___dimps_001.links.new(group_input.outputs["Blood Color"], mix_012.inputs[7])
    xenoverse___dimps_001.links.new(group_input.outputs["Blood Color"], mix_011.inputs[7])
    xenoverse___dimps_001.links.new(mix_012.outputs[2], mix_010.inputs[7])
    xenoverse___dimps_001.links.new(mix_011.outputs[2], mix_010.inputs[6])

    xenoverse___dimps_001.links.new(group_input.outputs["EMB Alpha"], invert.inputs[1])
    xenoverse___dimps_001.links.new(invert.outputs[0], math.inputs[0])
    xenoverse___dimps_001.links.new(group_input.outputs["EMB Line Thickness"], math.inputs[1])
    xenoverse___dimps_001.links.new(math.outputs[0], mix_002.inputs[7])

    # XVM DYT Color Override Path Links (UNCHANGED)
    xenoverse___dimps_001.links.new(group_input.outputs["Dual EMB Mask"],
                                    separate_dual_emb_mask_for_dyt_override.inputs[0])
    xenoverse___dimps_001.links.new(separate_dual_emb_mask_for_dyt_override.outputs[0], xvm_strength_multiply.inputs[0])
    xenoverse___dimps_001.links.new(group_input.outputs["Dual EMB Strength"], xvm_strength_multiply.inputs[1])
    xenoverse___dimps_001.links.new(xvm_strength_multiply.outputs[0], xvm_enable_multiply.inputs[0])
    xenoverse___dimps_001.links.new(group_input.outputs["Is XVM"], xvm_enable_multiply.inputs[1])
    xenoverse___dimps_001.links.new(xvm_enable_multiply.outputs[0], dyt_override_color_selector.inputs[0])
    xenoverse___dimps_001.links.new(group_input.outputs["DYT"], dyt_override_color_selector.inputs[6])
    xenoverse___dimps_001.links.new(group_input.outputs["Dual EMB Color"], dyt_override_color_selector.inputs[7])
    xenoverse___dimps_001.links.new(dyt_override_color_selector.outputs[2], mix_dyt_color_override_apply.inputs[6])

    # DYT Color Processing Path Links (UNCHANGED)
    xenoverse___dimps_001.links.new(group_input.outputs["DYT Color Override"], mix_dyt_color_override_apply.inputs[0])
    xenoverse___dimps_001.links.new(group_input.outputs["DYT Color"], mix_dyt_color_override_apply.inputs[7])
    xenoverse___dimps_001.links.new(mix_dyt_color_override_apply.outputs[2], hue_saturation_value.inputs[4])
    xenoverse___dimps_001.links.new(group_input.outputs["DYT Hue"], hue_saturation_value.inputs[0])
    xenoverse___dimps_001.links.new(group_input.outputs["DYT Saturation"], hue_saturation_value.inputs[1])
    xenoverse___dimps_001.links.new(group_input.outputs["DYT Value"], hue_saturation_value.inputs[2])
    xenoverse___dimps_001.links.new(hue_saturation_value.outputs[0], mix_002.inputs[6])

    # Combine DYT + Lines Links (UNCHANGED)
    xenoverse___dimps_001.links.new(mix_002.outputs[2], mix_012.inputs[7])
    xenoverse___dimps_001.links.new(mix_002.outputs[2], mix_011.inputs[6])

    # Apply Scratches & Blood Links (UNCHANGED)
    xenoverse___dimps_001.links.new(mix_010.outputs[2], mix_016.inputs[6])
    xenoverse___dimps_001.links.new(invert_004.outputs[0], mix_016.inputs[7])

    # TOON_UNIF_ENV Path Links (UNCHANGED)
    xenoverse___dimps_001.links.new(mix_016.outputs[2], toon_env_depth.inputs[6])
    xenoverse___dimps_001.links.new(group_input.outputs["EMB Color"], toon_env_depth.inputs[7])
    xenoverse___dimps_001.links.new(camera_fresnel_node.outputs[0], fresnel_power.inputs[0])
    xenoverse___dimps_001.links.new(fresnel_power.outputs[0], fresnel_factor.inputs[0])
    xenoverse___dimps_001.links.new(toon_env_depth.outputs[2], highlight_add.inputs[6])
    xenoverse___dimps_001.links.new(fresnel_factor.outputs[0], highlight_add.inputs[0])
    xenoverse___dimps_001.links.new(group_input.outputs["EMB Color"], highlight_add.inputs[7])

    xenoverse___dimps_001.links.new(group_input.outputs["Is TOON_UNIF_ENV"], toon_env_final_mix.inputs[0])
    xenoverse___dimps_001.links.new(mix_016.outputs[2], toon_env_final_mix.inputs[6])
    xenoverse___dimps_001.links.new(highlight_add.outputs[2], toon_env_final_mix.inputs[7])

    # Final Output Links (UNCHANGED)
    xenoverse___dimps_001.links.new(toon_env_final_mix.outputs[2], mix_shader.inputs[1])
    xenoverse___dimps_001.links.new(transparent_bsdf.outputs[0], mix_shader.inputs[2])
    xenoverse___dimps_001.links.new(group_input.outputs["Transparency"], mix_shader.inputs[0])
    xenoverse___dimps_001.links.new(mix_shader.outputs[0], group_output.inputs["Result"])

    return xenoverse___dimps_001


# UV_CACHE and related functions removed as per instructions.

def dyt_control__camera_based__node_group_def():  # Suffix _def
    if "DYT Control [CAMERA BASED]" in bpy.data.node_groups:
        return bpy.data.node_groups["DYT Control [CAMERA BASED]"]

    dyt_control__camera_based_ = bpy.data.node_groups.new(type='ShaderNodeTree', name="DYT Control [CAMERA BASED]")
    print("[XV2 DEBUG] Creating new 'DYT Control [CAMERA BASED]' node group.")

    X_OFFSET = 200
    Y_OFFSET = 150

    # Interface
    dyt_control__camera_based_.interface.new_socket(name="Vector", in_out='OUTPUT', socket_type='NodeSocketVector')
    s = dyt_control__camera_based_.interface.new_socket(name="DYT Line", in_out='INPUT', socket_type='NodeSocketFloat');
    s.default_value = 0.1
    s = dyt_control__camera_based_.interface.new_socket(name="DYT Light", in_out='INPUT',
                                                        socket_type='NodeSocketFloat');
    s.default_value = 1.0

    # Nodes
    group_input_1 = dyt_control__camera_based_.nodes.new("NodeGroupInput");
    group_input_1.name = "Group Input";
    group_input_1.location = (-X_OFFSET * 3, 0)
    group_output_1 = dyt_control__camera_based_.nodes.new("NodeGroupOutput");
    group_output_1.name = "Group Output";
    group_output_1.is_active_output = True;
    group_output_1.location = (X_OFFSET * 2, 0)

    math_002_1 = dyt_control__camera_based_.nodes.new("ShaderNodeMath");
    math_002_1.name = "Math.002";
    math_002_1.operation = 'MULTIPLY';
    math_002_1.inputs[1].default_value = 1.2;
    math_002_1.location = (-X_OFFSET * 2, Y_OFFSET)
    math_009 = dyt_control__camera_based_.nodes.new("ShaderNodeMath");
    math_009.name = "Math.009";
    math_009.operation = 'ADD';
    math_009.inputs[1].default_value = -0.2;
    math_009.location = (-X_OFFSET, Y_OFFSET)
    math_010 = dyt_control__camera_based_.nodes.new("ShaderNodeMath");
    math_010.name = "Math.010";
    math_010.operation = 'SUBTRACT';
    math_010.inputs[0].default_value = 1.9;
    math_010.location = (0, Y_OFFSET)

    geometry_001 = dyt_control__camera_based_.nodes.new("ShaderNodeNewGeometry");
    geometry_001.name = "Geometry.001";
    geometry_001.location = (-X_OFFSET * 2, -Y_OFFSET)
    vector_transform_001 = dyt_control__camera_based_.nodes.new("ShaderNodeVectorTransform");
    vector_transform_001.name = "Vector Transform.001";
    vector_transform_001.convert_from = 'WORLD';
    vector_transform_001.convert_to = 'CAMERA';
    vector_transform_001.vector_type = 'VECTOR';
    vector_transform_001.location = (-X_OFFSET, -Y_OFFSET)
    mapping = dyt_control__camera_based_.nodes.new("ShaderNodeMapping");
    mapping.name = "Mapping";
    mapping.vector_type = 'POINT';
    mapping.inputs[2].default_value = (-1.1170105934143066, 1.0838494300842285, 0.0);
    mapping.inputs[3].default_value = (1.899999976158142, 1.0, 1.0);
    mapping.location = (0, -Y_OFFSET)
    math_004 = dyt_control__camera_based_.nodes.new("ShaderNodeMath");
    math_004.name = "Math.004";
    math_004.operation = 'MULTIPLY';
    math_004.location = (X_OFFSET, -Y_OFFSET)

    combine_color_for_vector = dyt_control__camera_based_.nodes.new("ShaderNodeCombineColor");
    combine_color_for_vector.name = "Combine XYZ for Vector";
    combine_color_for_vector.inputs[0].default_value = 0.5;
    combine_color_for_vector.location = (0, 0)
    mapping_003 = dyt_control__camera_based_.nodes.new("ShaderNodeMapping");
    mapping_003.name = "Mapping.003";
    mapping_003.vector_type = 'POINT';
    mapping_003.inputs[3].default_value = (-0.7999997, 0.0, 0.0);
    mapping_003.location = (X_OFFSET, 0)

    # Links
    dyt_control__camera_based_.links.new(group_input_1.outputs["DYT Line"], math_002_1.inputs[0])
    dyt_control__camera_based_.links.new(math_002_1.outputs[0], math_009.inputs[0])
    dyt_control__camera_based_.links.new(math_009.outputs[0], math_010.inputs[1])
    dyt_control__camera_based_.links.new(math_010.outputs[0], combine_color_for_vector.inputs[1])

    dyt_control__camera_based_.links.new(geometry_001.outputs["Normal"], vector_transform_001.inputs[0])
    dyt_control__camera_based_.links.new(vector_transform_001.outputs[0], mapping.inputs[0])
    dyt_control__camera_based_.links.new(mapping.outputs[0], math_004.inputs[0])
    dyt_control__camera_based_.links.new(group_input_1.outputs["DYT Light"], math_004.inputs[1])
    dyt_control__camera_based_.links.new(math_004.outputs[0], mapping_003.inputs[0])

    dyt_control__camera_based_.links.new(combine_color_for_vector.outputs[0], mapping_003.inputs[1])
    dyt_control__camera_based_.links.new(mapping_003.outputs[0], group_output_1.inputs["Vector"])
    return dyt_control__camera_based_


# =============================================================================
# COMPLETE EYE SHADER SYSTEM REWRITE 
# =============================================================================

def dyt_control_node_group():
    """Create DYT Control node group """
    if "DYT Control" in bpy.data.node_groups:
        return bpy.data.node_groups["DYT Control"]

    dyt_control = bpy.data.node_groups.new(type='ShaderNodeTree', name="DYT Control")
    dyt_control.color_tag = 'NONE'
    dyt_control.description = ""

    # dyt_control interface
    # Socket Vector
    vector_socket = dyt_control.interface.new_socket(name="Vector", in_out='OUTPUT', socket_type='NodeSocketVector')
    vector_socket.default_value = (0.0, 0.0, 0.0)
    vector_socket.min_value = -3.4028234663852886e+38
    vector_socket.max_value = 3.4028234663852886e+38
    vector_socket.subtype = 'NONE'
    vector_socket.attribute_domain = 'POINT'

    # Socket DYT Line
    dyt_line_socket = dyt_control.interface.new_socket(name="DYT Line", in_out='INPUT', socket_type='NodeSocketFloat')
    dyt_line_socket.default_value = 0.10000002384185791
    dyt_line_socket.min_value = -10000.0
    dyt_line_socket.max_value = 10000.0
    dyt_line_socket.subtype = 'NONE'
    dyt_line_socket.attribute_domain = 'POINT'

    # Socket DYT Light
    dyt_light_socket = dyt_control.interface.new_socket(name="DYT Light", in_out='INPUT', socket_type='NodeSocketFloat')
    dyt_light_socket.default_value = 1.0
    dyt_light_socket.min_value = 0.0
    dyt_light_socket.max_value = 1.0
    dyt_light_socket.subtype = 'NONE'
    dyt_light_socket.attribute_domain = 'POINT'

    # initialize dyt_control nodes
    # node Math.010
    math_010 = dyt_control.nodes.new("ShaderNodeMath")
    math_010.name = "Math.010"
    math_010.operation = 'SUBTRACT'
    math_010.use_clamp = False
    math_010.inputs[0].default_value = 1.899999976158142  # Value

    # node Math.009
    math_009 = dyt_control.nodes.new("ShaderNodeMath")
    math_009.name = "Math.009"
    math_009.operation = 'ADD'
    math_009.use_clamp = False
    math_009.inputs[1].default_value = -0.20000001788139343  # Value_001

    # node Math.002
    math_002 = dyt_control.nodes.new("ShaderNodeMath")
    math_002.name = "Math.002"
    math_002.operation = 'MULTIPLY'
    math_002.use_clamp = False
    math_002.inputs[1].default_value = 1.2000000476837158  # Value_001

    # node Vector Math.001
    vector_math_001 = dyt_control.nodes.new("ShaderNodeVectorMath")
    vector_math_001.name = "Vector Math.001"
    vector_math_001.operation = 'DOT_PRODUCT'

    # node Vector Math.003
    vector_math_003 = dyt_control.nodes.new("ShaderNodeVectorMath")
    vector_math_003.name = "Vector Math.003"
    vector_math_003.operation = 'NORMALIZE'

    # node Math
    math = dyt_control.nodes.new("ShaderNodeMath")
    math.name = "Math"
    math.operation = 'ADD'
    math.use_clamp = False
    math.inputs[1].default_value = 0.0  # Value_001

    # node Group Output
    group_output = dyt_control.nodes.new("NodeGroupOutput")
    group_output.name = "Group Output"
    group_output.is_active_output = True

    # node Math.001
    math_001 = dyt_control.nodes.new("ShaderNodeMath")
    math_001.name = "Math.001"
    math_001.operation = 'MULTIPLY'
    math_001.use_clamp = False
    math_001.inputs[1].default_value = 0.49000003933906555  # Value_001

    # node Math.004
    math_004 = dyt_control.nodes.new("ShaderNodeMath")
    math_004.name = "Math.004"
    math_004.operation = 'MULTIPLY'
    math_004.use_clamp = False

    # node Mapping.003
    mapping_003 = dyt_control.nodes.new("ShaderNodeMapping")
    mapping_003.name = "Mapping.003"
    mapping_003.vector_type = 'POINT'
    mapping_003.inputs[2].default_value = (0.0, 0.0, 0.0)  # Rotation
    mapping_003.inputs[3].default_value = (1.0, 0.0, 0.0)  # Scale

    # node Combine RGB.003
    combine_rgb_003 = dyt_control.nodes.new("ShaderNodeCombineColor")
    combine_rgb_003.name = "Combine RGB.003"
    combine_rgb_003.mode = 'RGB'
    combine_rgb_003.inputs[0].default_value = 0.5  # Red
    combine_rgb_003.inputs[2].default_value = 0.0  # Blue

    # node Vector Math.013
    vector_math_013 = dyt_control.nodes.new("ShaderNodeVectorMath")
    vector_math_013.name = "Vector Math.013"
    vector_math_013.operation = 'SUBTRACT'

    # node Vector Math.010
    vector_math_010 = dyt_control.nodes.new("ShaderNodeVectorMath")
    vector_math_010.name = "Vector Math.010"
    vector_math_010.operation = 'SUBTRACT'
    vector_math_010.inputs[1].default_value = (0.0, 0.0, 1.0)  # Vector_001

    # node Object Info
    object_info = dyt_control.nodes.new("ShaderNodeObjectInfo")
    object_info.name = "Object Info"

    # node Geometry
    geometry = dyt_control.nodes.new("ShaderNodeNewGeometry")
    geometry.name = "Geometry"

    # node Vector Rotate
    vector_rotate = dyt_control.nodes.new("ShaderNodeVectorRotate")
    vector_rotate.name = "Vector Rotate"
    vector_rotate.invert = False
    vector_rotate.rotation_type = 'EULER_XYZ'
    vector_rotate.inputs[1].default_value = (0.0, 0.0, 0.0)  # Center
    vector_rotate.inputs[4].default_value = (-12.73259162902832, 0.7083449959754944, -8.709356307983398)  # Rotation

    # node Group Input
    group_input = dyt_control.nodes.new("NodeGroupInput")
    group_input.name = "Group Input"

    # node Vector Math
    vector_math = dyt_control.nodes.new("ShaderNodeVectorMath")
    vector_math.name = "Vector Math"
    vector_math.operation = 'NORMALIZE'

    # Set locations
    math_010.location = (-300.0, -20.0)
    math_009.location = (-400.0, -20.0)
    math_002.location = (-500.0, -20.0)
    vector_math_001.location = (-500.0, 0.0)
    vector_math_003.location = (-600.0, 0.0)
    math.location = (-400.0, 0.0)
    group_output.location = (0.0, 0.0)
    math_001.location = (-300.0, 0.0)
    math_004.location = (-200.0, 0.0)
    mapping_003.location = (-100.0, 0.0)
    combine_rgb_003.location = (-200.0, -20.0)
    vector_math_013.location = (-800.0, 0.0)
    vector_math_010.location = (-900.0, 0.0)
    object_info.location = (-1000.0, 0.0)
    geometry.location = (-700.0, 0.0)
    vector_rotate.location = (-700.0, -20.0)
    group_input.location = (-600.0, -40.0)
    vector_math.location = (-600.0, -20.0)

    # Set dimensions
    math_010.width, math_010.height = 140.0, 100.0
    math_009.width, math_009.height = 140.0, 100.0
    math_002.width, math_002.height = 140.0, 100.0
    vector_math_001.width, vector_math_001.height = 140.0, 100.0
    vector_math_003.width, vector_math_003.height = 140.0, 100.0
    math.width, math.height = 140.0, 100.0
    group_output.width, group_output.height = 140.0, 100.0
    math_001.width, math_001.height = 140.0, 100.0
    math_004.width, math_004.height = 140.0, 100.0
    mapping_003.width, mapping_003.height = 140.0, 100.0
    combine_rgb_003.width, combine_rgb_003.height = 140.0, 100.0
    vector_math_013.width, vector_math_013.height = 140.0, 100.0
    vector_math_010.width, vector_math_010.height = 140.0, 100.0
    object_info.width, object_info.height = 140.0, 100.0
    geometry.width, geometry.height = 140.0, 100.0
    vector_rotate.width, vector_rotate.height = 140.0, 100.0
    group_input.width, group_input.height = 140.0, 100.0
    vector_math.width, vector_math.height = 140.0, 100.0

    # initialize dyt_control links
    dyt_control.links.new(geometry.outputs[1], vector_math_003.inputs[0])  # geometry.Normal -> vector_math_003.Vector
    dyt_control.links.new(vector_math_003.outputs[0], vector_math_001.inputs[0])  # vector_math_003.Vector -> vector_math_001.Vector
    dyt_control.links.new(object_info.outputs[0], vector_math_010.inputs[0])  # object_info.Location -> vector_math_010.Vector
    dyt_control.links.new(object_info.outputs[0], vector_math_013.inputs[0])  # object_info.Location -> vector_math_013.Vector
    dyt_control.links.new(vector_math_010.outputs[0], vector_math_013.inputs[1])  # vector_math_010.Vector -> vector_math_013.Vector
    dyt_control.links.new(math.outputs[0], math_001.inputs[0])  # math.Value -> math_001.Value
    dyt_control.links.new(vector_math_001.outputs[1], math.inputs[0])  # vector_math_001.Value -> math.Value
    dyt_control.links.new(vector_math_013.outputs[0], vector_rotate.inputs[0])  # vector_math_013.Vector -> vector_rotate.Vector
    dyt_control.links.new(math_002.outputs[0], math_009.inputs[0])  # math_002.Value -> math_009.Value
    dyt_control.links.new(math_009.outputs[0], math_010.inputs[1])  # math_009.Value -> math_010.Value
    dyt_control.links.new(group_input.outputs[0], math_002.inputs[0])  # group_input.DYT Line -> math_002.Value
    dyt_control.links.new(mapping_003.outputs[0], group_output.inputs[0])  # mapping_003.Vector -> group_output.Vector
    dyt_control.links.new(math_010.outputs[0], combine_rgb_003.inputs[1])  # math_010.Value -> combine_rgb_003.Green
    dyt_control.links.new(math_001.outputs[0], math_004.inputs[0])  # math_001.Value -> math_004.Value
    dyt_control.links.new(group_input.outputs[1], math_004.inputs[1])  # group_input.DYT Light -> math_004.Value
    dyt_control.links.new(combine_rgb_003.outputs[0], mapping_003.inputs[1])  # combine_rgb_003.Color -> mapping_003.Location
    dyt_control.links.new(math_004.outputs[0], mapping_003.inputs[0])  # math_004.Value -> mapping_003.Vector
    dyt_control.links.new(vector_rotate.outputs[0], vector_math.inputs[0])  # vector_rotate.Vector -> vector_math.Vector
    dyt_control.links.new(vector_math.outputs[0], vector_math_001.inputs[1])  # vector_math.Vector -> vector_math_001.Vector

    return dyt_control


def xenoverse_eye_shader___dimps_node_group():
    """Create Xenoverse Eye Shader node group """
    if "Xenoverse Eye Shader - Dimps" in bpy.data.node_groups:
        return bpy.data.node_groups["Xenoverse Eye Shader - Dimps"]

    xenoverse_eye_shader___dimps = bpy.data.node_groups.new(type='ShaderNodeTree', name="Xenoverse Eye Shader - Dimps")
    xenoverse_eye_shader___dimps.color_tag = 'NONE'
    xenoverse_eye_shader___dimps.description = ""

    # xenoverse_eye_shader___dimps interface
    # Socket Result
    result_socket = xenoverse_eye_shader___dimps.interface.new_socket(name="Result", in_out='OUTPUT', socket_type='NodeSocketColor')
    result_socket.default_value = (0.0, 0.0, 0.0, 0.0)
    result_socket.attribute_domain = 'POINT'

    # Socket EMB Color
    emb_color_socket = xenoverse_eye_shader___dimps.interface.new_socket(name="EMB Color", in_out='INPUT', socket_type='NodeSocketColor')
    emb_color_socket.default_value = (0.800000011920929, 0.800000011920929, 0.800000011920929, 1.0)
    emb_color_socket.attribute_domain = 'POINT'

    # Socket Red Channel Push
    red_channel_push_socket = xenoverse_eye_shader___dimps.interface.new_socket(name="Red Channel Push", in_out='INPUT', socket_type='NodeSocketFloat')
    red_channel_push_socket.default_value = 0.20000001788139343
    red_channel_push_socket.min_value = -10000.0
    red_channel_push_socket.max_value = 10000.0
    red_channel_push_socket.subtype = 'NONE'
    red_channel_push_socket.attribute_domain = 'POINT'

    # Socket Green Channel Push
    green_channel_push_socket = xenoverse_eye_shader___dimps.interface.new_socket(name="Green Channel Push", in_out='INPUT', socket_type='NodeSocketFloat')
    green_channel_push_socket.default_value = 0.20000001788139343
    green_channel_push_socket.min_value = -10000.0
    green_channel_push_socket.max_value = 10000.0
    green_channel_push_socket.subtype = 'NONE'
    green_channel_push_socket.attribute_domain = 'POINT'

    # Socket Blue Channel Push
    blue_channel_push_socket = xenoverse_eye_shader___dimps.interface.new_socket(name="Blue Channel Push", in_out='INPUT', socket_type='NodeSocketFloat')
    blue_channel_push_socket.default_value = 0.23000001907348633
    blue_channel_push_socket.min_value = -10000.0
    blue_channel_push_socket.max_value = 10000.0
    blue_channel_push_socket.subtype = 'NONE'
    blue_channel_push_socket.attribute_domain = 'POINT'

    # Socket DYT Texture
    dyt_texture_socket = xenoverse_eye_shader___dimps.interface.new_socket(name="DYT Texture", in_out='INPUT', socket_type='NodeSocketColor')
    dyt_texture_socket.default_value = (1.0, 0.0, 0.004364978522062302, 1.0)
    dyt_texture_socket.attribute_domain = 'POINT'

    # Socket Line Art
    line_art_socket = xenoverse_eye_shader___dimps.interface.new_socket(name="Line Art", in_out='INPUT', socket_type='NodeSocketColor')
    line_art_socket.default_value = (1.0, 0.1569029837846756, 0.8885022401809692, 1.0)
    line_art_socket.attribute_domain = 'POINT'

    # Socket DYT Color Override
    dyt_color_override_socket = xenoverse_eye_shader___dimps.interface.new_socket(name="DYT Color Override", in_out='INPUT', socket_type='NodeSocketFloat')
    dyt_color_override_socket.default_value = 1.0
    dyt_color_override_socket.min_value = 0.0
    dyt_color_override_socket.max_value = 1.0
    dyt_color_override_socket.subtype = 'FACTOR'
    dyt_color_override_socket.attribute_domain = 'POINT'

    # Socket DYT Color
    dyt_color_socket = xenoverse_eye_shader___dimps.interface.new_socket(name="DYT Color", in_out='INPUT', socket_type='NodeSocketColor')
    dyt_color_socket.default_value = (0.5, 0.5, 0.5, 1.0)
    dyt_color_socket.attribute_domain = 'POINT'

    # Socket DYT Hue
    dyt_hue_socket = xenoverse_eye_shader___dimps.interface.new_socket(name="DYT Hue", in_out='INPUT', socket_type='NodeSocketFloat')
    dyt_hue_socket.default_value = 0.5
    dyt_hue_socket.min_value = 0.0
    dyt_hue_socket.max_value = 1.0
    dyt_hue_socket.subtype = 'NONE'
    dyt_hue_socket.attribute_domain = 'POINT'

    # Socket DYT Saturation
    dyt_saturation_socket = xenoverse_eye_shader___dimps.interface.new_socket(name="DYT Saturation", in_out='INPUT', socket_type='NodeSocketFloat')
    dyt_saturation_socket.default_value = 1.0
    dyt_saturation_socket.min_value = 0.0
    dyt_saturation_socket.max_value = 2.0
    dyt_saturation_socket.subtype = 'NONE'
    dyt_saturation_socket.attribute_domain = 'POINT'

    # Socket DYT Value
    dyt_value_socket = xenoverse_eye_shader___dimps.interface.new_socket(name="DYT Value", in_out='INPUT', socket_type='NodeSocketFloat')
    dyt_value_socket.default_value = 1.0
    dyt_value_socket.min_value = 0.0
    dyt_value_socket.max_value = 3.4028234663852886e+38
    dyt_value_socket.subtype = 'NONE'
    dyt_value_socket.attribute_domain = 'POINT'

    # Socket Green Area Color
    green_area_color_socket = xenoverse_eye_shader___dimps.interface.new_socket(name="Green Area Color", in_out='INPUT', socket_type='NodeSocketColor')
    green_area_color_socket.default_value = (0.8129027485847473, 1.0, 0.9005334973335266, 1.0)
    green_area_color_socket.attribute_domain = 'POINT'

    # initialize xenoverse_eye_shader___dimps nodes
    # node Reroute
    reroute = xenoverse_eye_shader___dimps.nodes.new("NodeReroute")
    reroute.name = "Reroute"

    # node Mix.003
    mix_003 = xenoverse_eye_shader___dimps.nodes.new("ShaderNodeMix")
    mix_003.name = "Mix.003"
    mix_003.blend_type = 'MIX'
    mix_003.clamp_factor = True
    mix_003.clamp_result = False
    mix_003.data_type = 'RGBA'
    mix_003.factor_mode = 'UNIFORM'
    mix_003.inputs[7].default_value = (0.0, 0.0, 0.0, 1.0)  # B_Color

    # node Invert
    invert = xenoverse_eye_shader___dimps.nodes.new("ShaderNodeInvert")
    invert.name = "Invert"
    invert.inputs[0].default_value = 1.0  # Fac

    # node Group Output
    group_output_1 = xenoverse_eye_shader___dimps.nodes.new("NodeGroupOutput")
    group_output_1.name = "Group Output"
    group_output_1.is_active_output = True

    # node Math.001
    math_001_1 = xenoverse_eye_shader___dimps.nodes.new("ShaderNodeMath")
    math_001_1.name = "Math.001"
    math_001_1.operation = 'GREATER_THAN'
    math_001_1.use_clamp = False

    # node Math
    math_1 = xenoverse_eye_shader___dimps.nodes.new("ShaderNodeMath")
    math_1.name = "Math"
    math_1.operation = 'GREATER_THAN'
    math_1.use_clamp = False

    # node Mix.001
    mix_001 = xenoverse_eye_shader___dimps.nodes.new("ShaderNodeMix")
    mix_001.name = "Mix.001"
    mix_001.blend_type = 'MIX'
    mix_001.clamp_factor = True
    mix_001.clamp_result = False
    mix_001.data_type = 'RGBA'
    mix_001.factor_mode = 'UNIFORM'

    # node Mix
    mix = xenoverse_eye_shader___dimps.nodes.new("ShaderNodeMix")
    mix.name = "Mix"
    mix.blend_type = 'MIX'
    mix.clamp_factor = True
    mix.clamp_result = False
    mix.data_type = 'RGBA'
    mix.factor_mode = 'UNIFORM'

    # node Mix.004
    mix_004 = xenoverse_eye_shader___dimps.nodes.new("ShaderNodeMix")
    mix_004.name = "Mix.004"
    mix_004.blend_type = 'COLOR'
    mix_004.clamp_factor = True
    mix_004.clamp_result = False
    mix_004.data_type = 'RGBA'
    mix_004.factor_mode = 'UNIFORM'

    # node Separate RGB
    separate_rgb = xenoverse_eye_shader___dimps.nodes.new("ShaderNodeSeparateColor")
    separate_rgb.name = "Separate RGB"
    separate_rgb.mode = 'RGB'

    # node Mix.002
    mix_002 = xenoverse_eye_shader___dimps.nodes.new("ShaderNodeMix")
    mix_002.name = "Mix.002"
    mix_002.blend_type = 'MIX'
    mix_002.clamp_factor = True
    mix_002.clamp_result = False
    mix_002.data_type = 'RGBA'
    mix_002.factor_mode = 'UNIFORM'

    # node Group Input
    group_input_1 = xenoverse_eye_shader___dimps.nodes.new("NodeGroupInput")
    group_input_1.name = "Group Input"

    # node Math.002
    math_002_1 = xenoverse_eye_shader___dimps.nodes.new("ShaderNodeMath")
    math_002_1.name = "Math.002"
    math_002_1.operation = 'GREATER_THAN'
    math_002_1.use_clamp = False

    # node Math.003
    math_003 = xenoverse_eye_shader___dimps.nodes.new("ShaderNodeMath")
    math_003.name = "Math.003"
    math_003.operation = 'GREATER_THAN'
    math_003.use_clamp = False
    math_003.inputs[0].default_value = 0.5  # Value
    math_003.inputs[1].default_value = 1.0  # Value_001

    # node Group Input.001
    group_input_001 = xenoverse_eye_shader___dimps.nodes.new("NodeGroupInput")
    group_input_001.name = "Group Input.001"

    # node Mix.005
    mix_005 = xenoverse_eye_shader___dimps.nodes.new("ShaderNodeMix")
    mix_005.name = "Mix.005"
    mix_005.blend_type = 'MULTIPLY'
    mix_005.clamp_factor = True
    mix_005.clamp_result = False
    mix_005.data_type = 'RGBA'
    mix_005.factor_mode = 'UNIFORM'

    # node Hue/Saturation/Value
    hue_saturation_value = xenoverse_eye_shader___dimps.nodes.new("ShaderNodeHueSaturation")
    hue_saturation_value.name = "Hue/Saturation/Value"
    hue_saturation_value.inputs[3].default_value = 1.0  # Fac

    # Set locations
    reroute.location = (-1210.0, -117.0)
    mix_003.location = (-1214.2958984375, -203.59786987304688)
    invert.location = (-1210.0, 0.0)
    group_output_1.location = (0.0, 0.0)
    math_001_1.location = (-795.8667602539062, 54.79131317138672)
    math_1.location = (-1449.6451416015625, -205.2508544921875)
    mix_001.location = (-490.0, -174.0)
    mix.location = (-730.0, -174.0)
    mix_004.location = (-966.801513671875, -208.7531280517578)
    separate_rgb.location = (-1627.33349609375, 154.81906127929688)
    mix_002.location = (-240.0, 0.0)
    group_input_1.location = (-1930.0, 0.0)
    math_002_1.location = (-502.9111633300781, 6.458605766296387)
    math_003.location = (-1470.7220458984375, 3.70210337638855)
    group_input_001.location = (-970.0, -488.0)
    mix_005.location = (-730.0, -418.0)
    hue_saturation_value.location = (-490.0, -418.0)

    # Set dimensions
    reroute.width, reroute.height = 16.0, 100.0
    mix_003.width, mix_003.height = 140.0, 100.0
    invert.width, invert.height = 140.0, 100.0
    group_output_1.width, group_output_1.height = 140.0, 100.0
    math_001_1.width, math_001_1.height = 140.0, 100.0
    math_1.width, math_1.height = 140.0, 100.0
    mix_001.width, mix_001.height = 140.0, 100.0
    mix.width, mix.height = 140.0, 100.0
    mix_004.width, mix_004.height = 140.0, 100.0
    separate_rgb.width, separate_rgb.height = 140.0, 100.0
    mix_002.width, mix_002.height = 140.0, 100.0
    group_input_1.width, group_input_1.height = 140.0, 100.0
    math_002_1.width, math_002_1.height = 140.0, 100.0
    math_003.width, math_003.height = 140.0, 100.0
    group_input_001.width, group_input_001.height = 140.0, 100.0
    mix_005.width, mix_005.height = 140.0, 100.0
    hue_saturation_value.width, hue_saturation_value.height = 150.0, 100.0

    # initialize xenoverse_eye_shader___dimps links
    xenoverse_eye_shader___dimps.links.new(reroute.outputs[0], mix.inputs[0])  # reroute.Output -> mix.Factor
    xenoverse_eye_shader___dimps.links.new(math_1.outputs[0], reroute.inputs[0])  # math_1.Value -> reroute.Input
    xenoverse_eye_shader___dimps.links.new(mix.outputs[2], mix_001.inputs[6])  # mix.Result -> mix_001.A
    xenoverse_eye_shader___dimps.links.new(math_001_1.outputs[0], mix_001.inputs[0])  # math_001_1.Value -> mix_001.Factor
    xenoverse_eye_shader___dimps.links.new(mix_001.outputs[2], mix_002.inputs[6])  # mix_001.Result -> mix_002.A
    xenoverse_eye_shader___dimps.links.new(math_002_1.outputs[0], mix_002.inputs[0])  # math_002_1.Value -> mix_002.Factor
    xenoverse_eye_shader___dimps.links.new(invert.outputs[0], mix_003.inputs[6])  # invert.Color -> mix_003.A
    xenoverse_eye_shader___dimps.links.new(mix_003.outputs[2], mix.inputs[6])  # mix_003.Result -> mix.A
    xenoverse_eye_shader___dimps.links.new(math_003.outputs[0], mix_003.inputs[0])  # math_003.Value -> mix_003.Factor
    xenoverse_eye_shader___dimps.links.new(math_003.outputs[0], invert.inputs[1])  # math_003.Value -> invert.Color
    xenoverse_eye_shader___dimps.links.new(reroute.outputs[0], mix_004.inputs[6])  # reroute.Output -> mix_004.A
    xenoverse_eye_shader___dimps.links.new(mix_004.outputs[2], mix.inputs[7])  # mix_004.Result -> mix.B
    xenoverse_eye_shader___dimps.links.new(reroute.outputs[0], mix_004.inputs[0])  # reroute.Output -> mix_004.Factor
    xenoverse_eye_shader___dimps.links.new(group_input_1.outputs[1], math_001_1.inputs[1])  # group_input_1.Red Channel Push -> math_001_1.Value
    xenoverse_eye_shader___dimps.links.new(group_input_1.outputs[2], math_1.inputs[1])  # group_input_1.Green Channel Push -> math_1.Value
    xenoverse_eye_shader___dimps.links.new(group_input_1.outputs[3], math_002_1.inputs[1])  # group_input_1.Blue Channel Push -> math_002_1.Value
    xenoverse_eye_shader___dimps.links.new(group_input_001.outputs[5], mix_001.inputs[7])  # group_input_001.Line Art -> mix_001.B
    xenoverse_eye_shader___dimps.links.new(separate_rgb.outputs[0], math_001_1.inputs[0])  # separate_rgb.Red -> math_001_1.Value
    xenoverse_eye_shader___dimps.links.new(separate_rgb.outputs[1], math_1.inputs[0])  # separate_rgb.Green -> math_1.Value
    xenoverse_eye_shader___dimps.links.new(separate_rgb.outputs[2], math_002_1.inputs[0])  # separate_rgb.Blue -> math_002_1.Value
    xenoverse_eye_shader___dimps.links.new(group_input_1.outputs[0], separate_rgb.inputs[0])  # group_input_1.EMB Color -> separate_rgb.Color
    xenoverse_eye_shader___dimps.links.new(mix_002.outputs[2], group_output_1.inputs[0])  # mix_002.Result -> group_output_1.Result
    xenoverse_eye_shader___dimps.links.new(group_input_001.outputs[4], mix_005.inputs[6])  # group_input_001.DYT Texture -> mix_005.A
    xenoverse_eye_shader___dimps.links.new(hue_saturation_value.outputs[0], mix_002.inputs[7])  # hue_saturation_value.Color -> mix_002.B
    xenoverse_eye_shader___dimps.links.new(mix_005.outputs[2], hue_saturation_value.inputs[4])  # mix_005.Result -> hue_saturation_value.Color
    xenoverse_eye_shader___dimps.links.new(group_input_001.outputs[6], mix_005.inputs[0])  # group_input_001.DYT Color Override -> mix_005.Factor
    xenoverse_eye_shader___dimps.links.new(group_input_001.outputs[8], hue_saturation_value.inputs[0])  # group_input_001.DYT Hue -> hue_saturation_value.Hue
    xenoverse_eye_shader___dimps.links.new(group_input_001.outputs[9], hue_saturation_value.inputs[1])  # group_input_001.DYT Saturation -> hue_saturation_value.Saturation
    xenoverse_eye_shader___dimps.links.new(group_input_001.outputs[10], hue_saturation_value.inputs[2])  # group_input_001.DYT Value -> hue_saturation_value.Value
    xenoverse_eye_shader___dimps.links.new(group_input_001.outputs[7], mix_005.inputs[7])  # group_input_001.DYT Color -> mix_005.B
    xenoverse_eye_shader___dimps.links.new(group_input_1.outputs[11], mix_004.inputs[7])  # group_input_1.Green Area Color -> mix_004.B

    return xenoverse_eye_shader___dimps
def setup_msk_as_inverted_xvm(mat, shader_type):
    """MSK detection: invert mask and route through XVM system with 2x strength"""
    if not mat or not mat.node_tree:
        return

    is_msk_shader = shader_type and "MSK" in shader_type.upper()
    if not is_msk_shader:
        return

    print(f"[XV2] MSK detected for '{mat.name}' - setting up as inverted XVM with 2x strength")

    dual_emb_node = mat.node_tree.nodes.get("Image Texture Dual EMB")
    group_node = mat.node_tree.nodes.get("Group")

    if not (dual_emb_node and group_node):
        return

    # Create/get invert node
    invert_msk = mat.node_tree.nodes.get("MSK Invert")
    if not invert_msk:
        invert_msk = mat.node_tree.nodes.new("ShaderNodeInvert")
        invert_msk.name = "MSK Invert"
        invert_msk.label = "MSK Mask Invert"
        invert_msk.location = dual_emb_node.location + mathutils.Vector((300, 0))
        invert_msk.inputs[0].default_value = 1.0

    # Set up connections and 2x strength
    dual_emb_mask_input = group_node.inputs.get("Dual EMB Mask")
    if dual_emb_mask_input:
        # Remove existing direct connection
        for link in list(mat.node_tree.links):
            if link.to_node == group_node and link.to_socket == dual_emb_mask_input:
                mat.node_tree.links.remove(link)

        # Route through invert
        mat.node_tree.links.new(dual_emb_node.outputs["Color"], invert_msk.inputs["Color"])
        mat.node_tree.links.new(invert_msk.outputs["Color"], dual_emb_mask_input)

        # Set 2x strength for MSK
        if "Is XVM" in group_node.inputs:
            group_node.inputs["Is XVM"].default_value = 2.0
        if "Dual EMB Strength" in group_node.inputs:
            group_node.inputs["Dual EMB Strength"].default_value = 2.0
            print(f"    MSK strength set to 2.0")


def xenoverse_2_eye___dimps_node_group(mat_node_tree):
    """Create eye material layout """

    # Clear existing nodes
    for node in list(mat_node_tree.nodes):
        mat_node_tree.nodes.remove(node)

    mat_node_tree.color_tag = 'NONE'
    mat_node_tree.description = ""

    # Ensure required node groups exist
    dyt_control = dyt_control_node_group()
    xenoverse_eye_shader___dimps = xenoverse_eye_shader___dimps_node_group()

    # initialize xenoverse_2_eye___dimps nodes
    # node Frame
    frame = mat_node_tree.nodes.new("NodeFrame")
    frame.label = "Line Work Image (sRGB)"
    frame.name = "Frame"
    frame.label_size = 20
    frame.shrink = True

    # node Frame.001
    frame_001 = mat_node_tree.nodes.new("NodeFrame")
    frame_001.label = "Eye Control"
    frame_001.name = "Frame.001"
    frame_001.label_size = 20
    frame_001.shrink = True

    # node DYT
    dyt = mat_node_tree.nodes.new("NodeFrame")
    dyt.label = "DYT Texture (sRGB)"
    dyt.name = "DYT"
    dyt.label_size = 20
    dyt.shrink = True

    # node Frame.002
    frame_002 = mat_node_tree.nodes.new("NodeFrame")
    frame_002.label = "EYE DYT'S WORK ON VALUES OF 0.07"
    frame_002.name = "Frame.002"
    frame_002.label_size = 20
    frame_002.shrink = True

    # node Material Output
    material_output = mat_node_tree.nodes.new("ShaderNodeOutputMaterial")
    material_output.name = "Material Output"
    material_output.is_active_output = True
    material_output.target = 'ALL'
    material_output.inputs[2].default_value = (0.0, 0.0, 0.0)  # Displacement
    material_output.inputs[3].default_value = 0.0  # Thickness

    # node Mapping
    mapping = mat_node_tree.nodes.new("ShaderNodeMapping")
    mapping.name = "Mapping"
    mapping.vector_type = 'POINT'
    mapping.inputs[2].default_value = (0.0, 0.0, 0.0)  # Rotation
    mapping.inputs[3].default_value = (1.0, 1.0, 1.0)  # Scale

    # node Texture Coordinate
    texture_coordinate = mat_node_tree.nodes.new("ShaderNodeTexCoord")
    texture_coordinate.name = "Texture Coordinate"
    texture_coordinate.from_instancer = False

    # node Normal
    normal = mat_node_tree.nodes.new("ShaderNodeNormal")
    normal.name = "Normal"
    normal.outputs[0].default_value = (0.0, 0.0, 1.0)

    # node Group
    group = mat_node_tree.nodes.new("ShaderNodeGroup")
    group.name = "Group"
    group.node_tree = dyt_control
    group.inputs[0].default_value = 0.16999998688697815  # Input_13
    group.inputs[1].default_value = 1.0  # Input_18

    # node Image Texture.004
    image_texture_004 = mat_node_tree.nodes.new("ShaderNodeTexImage")
    image_texture_004.name = "Image Texture.004"
    image_texture_004.extension = 'REPEAT'
    if "eye_R_dyt" in bpy.data.images:
        image_texture_004.image = bpy.data.images["eye_R_dyt"]
    image_texture_004.image_user.frame_current = 1
    image_texture_004.image_user.frame_duration = 1
    image_texture_004.image_user.frame_offset = -1
    image_texture_004.image_user.frame_start = 1
    image_texture_004.image_user.tile = 0
    image_texture_004.image_user.use_auto_refresh = False
    image_texture_004.image_user.use_cyclic = False
    image_texture_004.interpolation = 'Linear'
    image_texture_004.projection = 'FLAT'
    image_texture_004.projection_blend = 0.0

    # node Group.002
    group_002 = mat_node_tree.nodes.new("ShaderNodeGroup")
    group_002.name = "Group.002"
    group_002.node_tree = xenoverse_eye_shader___dimps
    group_002.inputs[1].default_value = 0.3499999940395355  # Input_2
    group_002.inputs[2].default_value = -0.09999999403953552  # Input_3
    group_002.inputs[3].default_value = 0.40000009536743164  # Input_4
    group_002.inputs[5].default_value = (0.0, 0.0, 0.0, 1.0)  # Input_6
    group_002.inputs[6].default_value = 0.0  # Input_11
    group_002.inputs[7].default_value = (0.3755105435848236, 0.3490547835826874, 0.4987925887107849, 1.0)  # Input_15
    group_002.inputs[8].default_value = 0.5  # Input_12
    group_002.inputs[9].default_value = 1.0  # Input_13
    group_002.inputs[10].default_value = 1.0  # Input_14

    # node Image Texture.001
    image_texture_001 = mat_node_tree.nodes.new("ShaderNodeTexImage")
    image_texture_001.name = "Image Texture.001"
    image_texture_001.extension = 'REPEAT'
    if "eye_L_000" in bpy.data.images:
        image_texture_001.image = bpy.data.images["eye_L_000"]
    image_texture_001.image_user.frame_current = 1
    image_texture_001.image_user.frame_duration = 1
    image_texture_001.image_user.frame_offset = -1
    image_texture_001.image_user.frame_start = 1
    image_texture_001.image_user.tile = 0
    image_texture_001.image_user.use_auto_refresh = False
    image_texture_001.image_user.use_cyclic = False
    image_texture_001.interpolation = 'Linear'
    image_texture_001.projection = 'FLAT'
    image_texture_001.projection_blend = 0.0

    # node DYT.001
    dyt_001 = mat_node_tree.nodes.new("NodeFrame")
    dyt_001.label = "DYT Texture (sRGB)"
    dyt_001.name = "DYT.001"
    dyt_001.label_size = 20
    dyt_001.shrink = True

    # node Frame.003
    frame_003 = mat_node_tree.nodes.new("NodeFrame")
    frame_003.label = "EYE DYT'S WORK ON VALUES OF 0.07"
    frame_003.name = "Frame.003"
    frame_003.label_size = 20
    frame_003.shrink = True

    # node Group.001
    group_001 = mat_node_tree.nodes.new("ShaderNodeGroup")
    group_001.name = "Group.001"
    group_001.node_tree = dyt_control
    group_001.inputs[0].default_value = 0.10000000149011612  # Input_13
    group_001.inputs[1].default_value = 1.0  # Input_18

    # node Image Texture.005
    image_texture_005 = mat_node_tree.nodes.new("ShaderNodeTexImage")
    image_texture_005.name = "Image Texture.005"
    image_texture_005.extension = 'REPEAT'
    if "eye_R_dyt" in bpy.data.images:
        image_texture_005.image = bpy.data.images["eye_R_dyt"]
    image_texture_005.image_user.frame_current = 1
    image_texture_005.image_user.frame_duration = 1
    image_texture_005.image_user.frame_offset = -1
    image_texture_005.image_user.frame_start = 1
    image_texture_005.image_user.tile = 0
    image_texture_005.image_user.use_auto_refresh = False
    image_texture_005.image_user.use_cyclic = False
    image_texture_005.interpolation = 'Linear'
    image_texture_005.projection = 'FLAT'
    image_texture_005.projection_blend = 0.0

    # node Mix
    mix_1 = mat_node_tree.nodes.new("ShaderNodeMix")
    mix_1.name = "Mix"
    mix_1.blend_type = 'MIX'
    mix_1.clamp_factor = True
    mix_1.clamp_result = True
    mix_1.data_type = 'RGBA'
    mix_1.factor_mode = 'UNIFORM'
    mix_1.inputs[7].default_value = (0.3499999940395355, 0.3499999940395355, 0.3499999940395355, 1.0)  # B_Color

    # Set parents
    frame_001.parent = frame
    frame_002.parent = dyt
    mapping.parent = frame_001
    texture_coordinate.parent = frame_001
    normal.parent = frame_001
    group.parent = frame_002
    image_texture_004.parent = dyt
    image_texture_001.parent = frame
    frame_003.parent = dyt_001
    group_001.parent = frame_003
    image_texture_005.parent = dyt_001

    # Set locations
    frame.location = (-810.7117919921875, 603.7999877929688)
    frame_001.location = (804.54248046875, -697.4236450195312)
    dyt.location = (380.0831298828125, -388.9222106933594)
    frame_002.location = (-324.9755859375, 232.99676513671875)
    material_output.location = (414.27972412109375, -36.549560546875)
    mapping.location = (-915.2491455078125, 19.9918212890625)
    texture_coordinate.location = (-1395.2491455078125, 19.9918212890625)
    normal.location = (-1155.2491455078125, 19.9918212890625)
    group.location = (-914.9616088867188, -322.746337890625)
    image_texture_004.location = (-913.3623657226562, -14.52142333984375)
    group_002.location = (-56.85869598388672, 3.802694320678711)
    image_texture_001.location = (197.0001220703125, -662.7601928710938)
    dyt_001.location = (403.7572021484375, -774.8160400390625)
    frame_003.location = (-324.9755859375, 232.99676513671875)
    group_001.location = (-914.9616088867188, -322.746337890625)
    image_texture_005.location = (-665.578369140625, 174.593994140625)
    mix_1.location = (-272.948974609375, 48.62162399291992)

    # Set dimensions
    frame.width, frame.height = 1117.0, 425.0
    frame_001.width, frame_001.height = 680.0, 355.0
    dyt.width, dyt.height = 654.1712646484375, 341.0
    frame_002.width, frame_002.height = 200.0, 189.0
    material_output.width, material_output.height = 140.0, 100.0
    mapping.width, mapping.height = 140.0, 100.0
    texture_coordinate.width, texture_coordinate.height = 140.0, 100.0
    normal.width, normal.height = 140.0, 100.0
    group.width, group.height = 140.0, 100.0
    image_texture_004.width, image_texture_004.height = 237.17123413085938, 100.0
    group_002.width, group_002.height = 222.1776123046875, 100.0
    image_texture_001.width, image_texture_001.height = 240.0, 100.0
    dyt_001.width, dyt_001.height = 901.1712646484375, 484.0
    frame_003.width, frame_003.height = 200.0, 189.0
    group_001.width, group_001.height = 140.0, 100.0
    image_texture_005.width, image_texture_005.height = 237.17123413085938, 100.0
    mix_1.width, mix_1.height = 140.0, 100.0

    # initialize xenoverse_2_eye___dimps links
    mat_node_tree.links.new(texture_coordinate.outputs[2], normal.inputs[0])  # texture_coordinate.UV -> normal.Normal
    mat_node_tree.links.new(normal.outputs[0], mapping.inputs[1])  # normal.Normal -> mapping.Location
    mat_node_tree.links.new(texture_coordinate.outputs[2], mapping.inputs[0])  # texture_coordinate.UV -> mapping.Vector
    mat_node_tree.links.new(group_002.outputs[0], material_output.inputs[0])  # group_002.Result -> material_output.Surface
    mat_node_tree.links.new(group.outputs[0], image_texture_004.inputs[0])  # group.Vector -> image_texture_004.Vector
    mat_node_tree.links.new(image_texture_004.outputs[0], group_002.inputs[4])  # image_texture_004.Color -> group_002.DYT Texture
    mat_node_tree.links.new(mapping.outputs[0], image_texture_001.inputs[0])  # mapping.Vector -> image_texture_001.Vector
    mat_node_tree.links.new(group_001.outputs[0], image_texture_005.inputs[0])  # group_001.Vector -> image_texture_005.Vector
    mat_node_tree.links.new(image_texture_001.outputs[1], mix_1.inputs[0])  # image_texture_001.Alpha -> mix_1.Factor
    mat_node_tree.links.new(image_texture_001.outputs[0], mix_1.inputs[2])  # image_texture_001.Color -> mix_1.A
    mat_node_tree.links.new(image_texture_001.outputs[0], mix_1.inputs[6])  # image_texture_001.Color -> mix_1.A
    mat_node_tree.links.new(mix_1.outputs[2], group_002.inputs[0])  # mix_1.Result -> group_002.EMB Color
    mat_node_tree.links.new(image_texture_005.outputs[0], group_002.inputs[11])  # image_texture_005.Color -> group_002.Green Area Color

    return mat_node_tree


# Eye shader detection and configuration
def is_eye_shader(shader_type):
    """Check if shader type is an eye shader"""
    return shader_type and "EYE" in shader_type.upper()


def get_eye_shader_config(shader_type):
    """Get configuration for eye shaders based on MUT type"""
    if not shader_type:
        return {
            'red_channel_push': 0.35,
            'green_channel_push': -0.1,
            'blue_channel_push': 0.4,
        }

    shader_upper = shader_type.upper()

    # Extract MUT type from shader name
    if 'MUT0' in shader_upper:
        return {
            'red_channel_push': 0.1,
            'green_channel_push': -0.1,
            'blue_channel_push': 0.4,
        }
    elif 'MUT1' in shader_upper:
        return {
            'red_channel_push': 0.2,
            'green_channel_push': -0.1,
            'blue_channel_push': 0.3,
        }
    elif 'MUT2' in shader_upper:
        return {
            'red_channel_push': 0.25,
            'green_channel_push': -0.1,
            'blue_channel_push': 0.4,
        }
    elif 'MUT3' in shader_upper:
        return {
            'red_channel_push': 0.35,
            'green_channel_push': 0.2,
            'blue_channel_push': 0.4,
        }
    else:
        # Fallback values
        return {
            'red_channel_push': 0.35,
            'green_channel_push': -0.1,
            'blue_channel_push': 0.4,
        }


def create_eye_material(material_name, shader_type="", primary_stub="", rows=None):
    """Create eye material using the exact pattern"""
    print(f"[XV2 Eye] Creating eye material: {material_name} (shader: {shader_type})")

    # Create or get material
    mat = bpy.data.materials.get(material_name)
    if not mat:
        mat = bpy.data.materials.new(name=material_name)

    mat.use_nodes = True

    # Create the node tree
    xenoverse_2_eye___dimps_node_group(mat.node_tree)
    mat_scale1x = rows.get(primary_stub.lower(), 0) if rows else 0
    primary_dyt_line = (mat_scale1x + 1) * 0.1 + 0.07
    secondary_dyt_line = (mat_scale1x + 1) * 0.10  # Secondary uses 0.10 multiplier

    # Apply calculated DYT line values to eye shader nodes
    group_primary = mat.node_tree.nodes.get("Group")  # Primary DYT control
    group_secondary = mat.node_tree.nodes.get("Group.001")  # Secondary DYT control

    if group_primary and len(group_primary.inputs) > 0:
        group_primary.inputs[0].default_value = primary_dyt_line  # DYT Line input
        print(f"[XV2 Eye] Set primary DYT Line to {primary_dyt_line:.3f} for {material_name}")

    if group_secondary and len(group_secondary.inputs) > 0:
        group_secondary.inputs[0].default_value = secondary_dyt_line  # DYT Line input
        print(f"[XV2 Eye] Set secondary DYT Line to {secondary_dyt_line:.3f} for {material_name}")

    # Apply eye-specific settings to the Group.002 node (the eye shader)
    eye_config = get_eye_shader_config(shader_type)
    group_002 = mat.node_tree.nodes.get("Group.002")
    if group_002:
        group_002.inputs[1].default_value = eye_config['red_channel_push']    # Red Channel Push
        group_002.inputs[2].default_value = eye_config['green_channel_push']  # Green Channel Push
        group_002.inputs[3].default_value = eye_config['blue_channel_push']   # Blue Channel Push

    return mat


def analyze_mask_type(image):
    """Determine if mask is grayscale (R=G=B), single-channel, or multi-channel"""
    if not image or not hasattr(image, 'pixels') or len(image.pixels) == 0:
        return "unknown"

    try:
        pixels = list(image.pixels)
        if len(pixels) < 4:
            return "unknown"

        # Sample first 100 pixels to determine mask type
        sample_size = min(400, len(pixels))  # 100 pixels * 4 channels

        grayscale_count = 0
        single_channel_count = 0
        multi_channel_count = 0

        for i in range(0, sample_size, 4):
            r, g, b = pixels[i], pixels[i + 1], pixels[i + 2]

            # Skip completely black pixels
            if r < 0.01 and g < 0.01 and b < 0.01:
                continue

            # Check if this pixel is grayscale (R=G=B)
            if abs(r - g) < 0.01 and abs(g - b) < 0.01 and abs(r - b) < 0.01:
                grayscale_count += 1
            else:
                # Count how many channels have significant data
                channels_with_data = sum([r > 0.01, g > 0.01, b > 0.01])

                if channels_with_data == 1:
                    single_channel_count += 1
                elif channels_with_data > 1:
                    multi_channel_count += 1

        total_samples = grayscale_count + single_channel_count + multi_channel_count

        if total_samples == 0:
            return "unknown"

        # Determine mask type based on majority
        if grayscale_count > (total_samples * 0.7):
            return "grayscale"
        elif single_channel_count > (total_samples * 0.7):
            return "single_channel"
        elif multi_channel_count > (total_samples * 0.4):  # Lower threshold since it's a new category
            return "multi_channel"
        else:
            return "unknown"

    except Exception as e:
        print(f"[XV2 Eye] Error analyzing mask type: {e}")
        return "unknown"


def calculate_channel_pushes_from_mask(mask_image):
    """Calculate optimal channel push values based on mask analysis"""

    mask_type = analyze_mask_type(mask_image)

    print(f"[XV2 Eye] Detected mask type: {mask_type}")

    if mask_type == "grayscale":
        # Grayscale mask (R=G=B): like eye_R_000.dds
        return {
            'red_channel_push': 0.20,
            'green_channel_push': -0.1,
            'blue_channel_push': 0.3
        }
    elif mask_type == "single_channel":
        # Single-channel mask: like eye_R_001.dds, eye_L_000.dds
        return {
            'red_channel_push': 0.15,
            'green_channel_push': -0.1,
            'blue_channel_push': 0.4
        }
    elif mask_type == "multi_channel":
        # Multi-channel mask: mixed G+B channels
        return {
            'red_channel_push': 0.1,
            'green_channel_push': -0.1,
            'blue_channel_push': 0.35
        }
    else:
        # Fallback to safe defaults
        print(f"[XV2 Eye] Unknown mask type, using fallback values")
        return {
            'red_channel_push': 0.15,
            'green_channel_push': -0.1,
            'blue_channel_push': 0.35
        }


def assign_eye_textures(mat, primary_stub, original_material_name, tex_root):
    """Assign textures to eye material, now with _001 support and mask analysis."""
    if not mat or not mat.node_tree:
        return
    print(f"[XV2 Eye] Assigning textures for: {mat.name}")

    # Get texture nodes from the eye material layout
    eye_main_node = mat.node_tree.nodes.get("Image Texture.001")  # This is the main EMB texture node
    dyt_004_node = mat.node_tree.nodes.get("Image Texture.004")  # Main DYT
    dyt_005_node = mat.node_tree.nodes.get("Image Texture.005")  # Green area DYT (often same as main)

    # Search for textures
    img_000 = find_image(primary_stub, original_material_name, "000", tex_root)
    img_001 = find_image(primary_stub, original_material_name, "001", tex_root)
    img_dyt = find_image(primary_stub, original_material_name, "dyt", tex_root)

    # Assign eye texture with _001 as a fallback
    assigned_eye_tex = None
    assigned_mask_tex = None

    if eye_main_node:
        if img_000:
            assigned_eye_tex = img_000
            print(f"[XV2 Eye] Main eye texture (000): {img_000.name}")
        elif img_001:
            assigned_eye_tex = img_001
            print(f"[XV2 Eye] Main eye texture (fallback to 001): {img_001.name}")

        if assigned_eye_tex:
            eye_main_node.image = assigned_eye_tex
        else:
            eye_main_node.image = None
            print(f"[XV2 Eye] Main eye texture (000/001): NONE")

    # Determine which texture to use for mask analysis
    # Priority: 001 for masks, then 000 as fallback
    if img_001:
        assigned_mask_tex = img_001
        print(f"[XV2 Eye] Using 001 texture for mask analysis: {img_001.name}")
    elif img_000:
        assigned_mask_tex = img_000
        print(f"[XV2 Eye] Using 000 texture for mask analysis: {img_000.name}")

    # Assign DYT textures
    if img_dyt:
        if dyt_004_node:
            dyt_004_node.image = img_dyt
            print(f"[XV2 Eye] Main DYT: {img_dyt.name}")
        if dyt_005_node:
            dyt_005_node.image = img_dyt
            print(f"[XV2 Eye] Green area DYT: {img_dyt.name}")

    # Apply mask-analyzed channel pushes
    group_002 = mat.node_tree.nodes.get("Group.002")  # The eye shader group
    if group_002 and assigned_mask_tex:
        # Analyze the mask texture to get optimal channel push values
        eye_config = calculate_channel_pushes_from_mask(assigned_mask_tex)

        # Apply the analyzed channel push values
        if len(group_002.inputs) > 1:
            group_002.inputs[1].default_value = eye_config['red_channel_push']  # Red Channel Push
        if len(group_002.inputs) > 2:
            group_002.inputs[2].default_value = eye_config['green_channel_push']  # Green Channel Push
        if len(group_002.inputs) > 3:
            group_002.inputs[3].default_value = eye_config['blue_channel_push']  # Blue Channel Push

        print(
            f"[XV2 Eye] Applied mask-analyzed channel pushes: R={eye_config['red_channel_push']}, G={eye_config['green_channel_push']}, B={eye_config['blue_channel_push']}")
    else:
        print(f"[XV2 Eye] No mask texture available for analysis, using fallback channel pushes")
        # Apply safe fallback values
        if group_002:
            if len(group_002.inputs) > 1:
                group_002.inputs[1].default_value = 0.15  # Red fallback
            if len(group_002.inputs) > 2:
                group_002.inputs[2].default_value = -0.1  # Green fallback
            if len(group_002.inputs) > 3:
                group_002.inputs[3].default_value = 0.35  # Blue fallback


# Integration functions to replace existing ones
def create_xv2_material_enhanced(material_name, shader_type="", primary_stub="", rows=None, texture_folder=""):
    """Enhanced material creation that handles both regular and eye shaders"""
    if is_eye_shader(shader_type):
        return create_eye_material(material_name, shader_type, primary_stub, rows or {})
    else:
        return create_xv2_material(material_name)


def assign_images_enhanced(mat, primary_stub, original_material_name, tex_root, shader_type="", mat_scale1x_val=None):
    """Enhanced image assignment that handles both regular and eye shaders"""
    if is_eye_shader(shader_type):
        assign_eye_textures(mat, primary_stub, original_material_name, tex_root)
    else:
        assign_images(mat, primary_stub, original_material_name, tex_root, shader_type, mat_scale1x_val)


# ADD THIS TO YOUR MAIN REGISTRATION FUNCTION:
def ensure_eye_node_groups():
    """Ensure eye shader node groups are available"""
    if "DYT Control" not in bpy.data.node_groups:
        dyt_control_node_group()
        print("[XV2 Eye] Created DYT Control node group")

    if "Xenoverse Eye Shader - Dimps" not in bpy.data.node_groups:
        xenoverse_eye_shader___dimps_node_group()
        print("[XV2 Eye] Created Xenoverse Eye Shader - Dimps node group")


def ensure_node_group(name, create_fn_def):
    if name not in bpy.data.node_groups:
        print(f"[XV2] Node group '{name}' not found, creating it via definition.")
        return create_fn_def()

    # For "Xenoverse - Dimps.001", ensure it's the latest version by calling the def function
    # which now has a check and recreate logic if outdated.
    if name == "Xenoverse - Dimps.001":
        return create_fn_def()

    return bpy.data.node_groups[name]


def setup_dual_emb_color(mat, shader_type=""):
    """Set up DYT dual color sampling for Dual EMB Masks OR MSK AO."""
    dyt_texture_node = mat.node_tree.nodes.get("Image Texture.004")
    group_node = mat.node_tree.nodes.get("Group")

    if not (dyt_texture_node and dyt_texture_node.image and group_node and "Dual EMB Color" in group_node.inputs):
        return

    is_msk = shader_type and "MSK" in shader_type.upper()
    # is_xvm = shader_type and "XVM" in shader_type.upper() # Not directly used for UV choice here, is_msk is primary driver

    old_sampler_name = "DYT Dual Color Sampler"
    old_uv_map_name = "Dual Color UV Map"

    # Remove existing nodes if they are there to ensure clean setup
    if mat.node_tree.nodes.get(old_sampler_name):
        mat.node_tree.nodes.remove(mat.node_tree.nodes[old_sampler_name])
    if mat.node_tree.nodes.get(old_uv_map_name):
        mat.node_tree.nodes.remove(mat.node_tree.nodes[old_uv_map_name])

    dyt_dual_sampler = mat.node_tree.nodes.new("ShaderNodeTexImage")
    dyt_dual_sampler.name = old_sampler_name
    # Label reflects what the "Dual EMB Color" input is used for based on shader type
    # If MSK, it samples X=0.1. If XVM (or other), it samples Y=0.9.
    dyt_dual_sampler.label = f"DYT Sample for 'Dual EMB Color' (X0.1 if MSK, Y0.9 else)"
    dyt_dual_sampler.location = group_node.location + mathutils.Vector((-300, -550))
    dyt_dual_sampler.image = dyt_texture_node.image
    dyt_dual_sampler.hide = True

    dual_uv_map = mat.node_tree.nodes.new("ShaderNodeMapping")
    dual_uv_map.name = old_uv_map_name
    dual_uv_map.label = "UV for 'Dual EMB Color' Sample"
    dual_uv_map.location = dyt_dual_sampler.location + mathutils.Vector((-200, 0))

    if is_msk:  # This condition is from the original logic for this function
        # For MSK-identified materials, "Dual EMB Color" input gets DYT sampled at X=0.1
        dual_uv_map.inputs["Location"].default_value[0] = 0.1
        dual_uv_map.inputs["Location"].default_value[1] = 0.0
    else:
        # For non-MSK (e.g., XVM), "Dual EMB Color" input gets DYT sampled at Y=0.9
        dual_uv_map.inputs["Location"].default_value[0] = 0.0
        dual_uv_map.inputs["Location"].default_value[1] = 0.9

    dual_uv_map.hide = True

    dyt_uv_source_socket = None
    dyt_main_tex_node = mat.node_tree.nodes.get("Image Texture.004")
    if dyt_main_tex_node:
        # Find what's connected to the DYT texture's Vector input (usually the DYT Control group)
        dyt_uv_source_socket = next((link.from_socket for link in mat.node_tree.links if
                                     link.to_node == dyt_main_tex_node and link.to_socket == dyt_main_tex_node.inputs[
                                         "Vector"]), None)

    if dyt_uv_source_socket:
        mat.node_tree.links.new(dyt_uv_source_socket, dual_uv_map.inputs["Vector"])
        mat.node_tree.links.new(dual_uv_map.outputs["Vector"], dyt_dual_sampler.inputs["Vector"])

        target_socket = group_node.inputs["Dual EMB Color"]
        # Remove any existing links to this target socket before adding new one
        for link in list(mat.node_tree.links):
            if link.to_node == group_node and link.to_socket == target_socket:
                mat.node_tree.links.remove(link)
        mat.node_tree.links.new(dyt_dual_sampler.outputs["Color"], target_socket)
    else:
        print(f"[XV2][DualEMBSamplerSetup] '{mat.name}': No UV source for DYT. 'Dual EMB Color' sampling skipped.")


def xenoverse_2___dimps_node_group(node_tree):
    for node in list(node_tree.nodes): node_tree.nodes.remove(node)

    # Frames for texture nodes
    dyt_frame = node_tree.nodes.new("NodeFrame");
    dyt_frame.label = "DYT Texture (sRGB)";
    dyt_frame.name = "DYT Frame";
    dyt_frame.label_size = 20;
    dyt_frame.shrink = True
    emb_frame = node_tree.nodes.new("NodeFrame");
    emb_frame.label = "Line Work Image (sRGB)";
    emb_frame.name = "EMB Frame";
    emb_frame.label_size = 20;
    emb_frame.shrink = True
    dual_emb_texture_frame = node_tree.nodes.new("NodeFrame");
    dual_emb_texture_frame.label = "MSK / XVM Mask Texture";  # Updated label
    dual_emb_texture_frame.name = "Dual EMB Texture Frame";
    dual_emb_texture_frame.label_size = 20;
    dual_emb_texture_frame.shrink = True

    material_output = node_tree.nodes.new("ShaderNodeOutputMaterial");
    material_output.name = "Material Output";
    material_output.is_active_output = True

    # Texture Nodes
    image_texture_004 = node_tree.nodes.new("ShaderNodeTexImage");
    image_texture_004.name = "Image Texture.004";
    image_texture_004.label = "DYT Image";
    image_texture_004.parent = dyt_frame;
    image_texture_004.location = (0, -75)
    image_texture_001 = node_tree.nodes.new("ShaderNodeTexImage");
    image_texture_001.name = "Image Texture.001";
    image_texture_001.label = "EMB Image (000)";
    image_texture_001.parent = emb_frame;
    image_texture_001.location = (0, 0)
    image_texture_dual_emb = node_tree.nodes.new("ShaderNodeTexImage");
    image_texture_dual_emb.name = "Image Texture Dual EMB";
    image_texture_dual_emb.label = "Mask (e.g., _001, _002)";  # Updated label
    image_texture_dual_emb.parent = dual_emb_texture_frame;
    image_texture_dual_emb.location = (0, 0)

    # Main Shader Group
    group = node_tree.nodes.new("ShaderNodeGroup");
    group.name = "Group";
    group.label = "Xenoverse Dimps Shader"
    group.node_tree = ensure_node_group("Xenoverse - Dimps.001", xenoverse___dimps_001_node_group_def)

    # DYT UV Control Group
    group_002 = node_tree.nodes.new("ShaderNodeGroup");
    group_002.name = "Group.002";
    group_002.label = "DYT UV Control";
    group_002.parent = dyt_frame;
    group_002.location = (0, 75)
    group_002.node_tree = ensure_node_group("DYT Control [CAMERA BASED]", dyt_control__camera_based__node_group_def)
    if "DYT Line" in group_002.inputs: group_002.inputs["DYT Line"].default_value = 0.1
    if "DYT Light" in group_002.inputs: group_002.inputs["DYT Light"].default_value = 1.0

    # Positioning of Frames and Output
    FRAME_X_COL1 = -1300
    FRAME_X_COL2 = -950
    GROUP_X = -400  # Main shader group X
    OUTPUT_X = GROUP_X + 2200  # Adjusted for wider main group, group output is at 2000

    emb_frame.location = (FRAME_X_COL1, 150)
    dual_emb_texture_frame.location = (FRAME_X_COL1, -150)
    dyt_frame.location = (FRAME_X_COL2, 0)
    group.location = (GROUP_X, 0)
    material_output.location = (OUTPUT_X, 0)

    # Links
    node_tree.links.new(image_texture_001.outputs["Color"], group.inputs["EMB Color"])
    node_tree.links.new(image_texture_001.outputs["Alpha"], group.inputs["EMB Alpha"])
    node_tree.links.new(image_texture_004.outputs["Color"], group.inputs["DYT"])
    node_tree.links.new(group_002.outputs["Vector"], image_texture_004.inputs["Vector"])
    node_tree.links.new(image_texture_dual_emb.outputs["Color"], group.inputs["Dual EMB Mask"])
    node_tree.links.new(group.outputs["Result"], material_output.inputs["Surface"])
    return node_tree


def build_row_map(folder):
    rows = {}
    shader_types = {}
    if not isinstance(folder, str) or not folder or not os.path.isdir(folder):
        print(f"[XV2] EMM XML folder path is not set or invalid: '{folder}'. Skipping EMM data loading.")
        return rows, shader_types
    for root, _, files in os.walk(folder):
        for f in files:
            if f.endswith(".emm.xml"):
                try:
                    xml_path = os.path.join(root, f)
                    tree = ET.parse(xml_path)
                    xml_root = tree.getroot()
                except ET.ParseError:
                    print(f"[XV2] Warning: Could not parse EMM XML: {xml_path}")
                    continue
                for m in xml_root.findall(".//Material"):
                    name_attr = m.get("Name")
                    shader_attr = m.get("Shader")
                    if name_attr is None: continue
                    name = name_attr.lower()
                    if shader_attr: shader_types[name] = shader_attr
                    mat_scale_param = next((p for p in m.findall('.//Parameter') if p.get("Name") == "MatScale1X"),
                                           None)
                    if mat_scale_param is not None and mat_scale_param.get("value") is not None:
                        try:
                            rows[name] = int(float(mat_scale_param.get("value")))
                        except ValueError:
                            print(f"[XV2] Warning: Could not parse MatScale1X for EMM material '{name}' in {f}")
    return rows, shader_types


def setup_toon_unif_env_camera_uvs(mat, obj=None):
    if not mat or not mat.node_tree:
        return

    emb_tex_node = mat.node_tree.nodes.get("Image Texture.001")
    if not emb_tex_node:
        return

    if mat.node_tree.nodes.get("TOON_UNIF_ENV Tex Coord"):
        return

    X_OFFSET = 250
    BASE_X = emb_tex_node.location[0] - X_OFFSET * 3
    BASE_Y = emb_tex_node.location[1] - X_OFFSET

    tex_coord_node = mat.node_tree.nodes.new("ShaderNodeTexCoord")
    tex_coord_node.name = "TOON_UNIF_ENV Tex Coord"
    tex_coord_node.from_instancer = True
    tex_coord_node.location = (BASE_X, BASE_Y)
    tex_coord_node.hide = True

    vec_transform = mat.node_tree.nodes.new("ShaderNodeVectorTransform")
    vec_transform.name = "TOON_UNIF_ENV Transform"
    vec_transform.convert_from = 'OBJECT'
    vec_transform.convert_to = 'CAMERA'
    vec_transform.vector_type = 'NORMAL'
    vec_transform.location = (BASE_X + X_OFFSET, BASE_Y)
    vec_transform.hide = True

    mapping_node = mat.node_tree.nodes.new("ShaderNodeMapping")
    mapping_node.name = "TOON_UNIF_ENV Mapping"
    mapping_node.vector_type = 'POINT'
    mapping_node.location = (BASE_X + X_OFFSET * 2, BASE_Y)

    mapping_node.inputs["Location"].default_value = (0.5, 0.5, 0.0)
    mapping_node.inputs["Rotation"].default_value = (0.0, 0.0, 0.0)
    mapping_node.inputs["Scale"].default_value = (0.5, -0.5, 0.0)

    mat.node_tree.links.new(tex_coord_node.outputs["Normal"], vec_transform.inputs["Vector"])
    mat.node_tree.links.new(vec_transform.outputs["Vector"], mapping_node.inputs["Vector"])

    for link in list(mat.node_tree.links):
        if link.to_node == emb_tex_node and link.to_socket == emb_tex_node.inputs["Vector"]:
            mat.node_tree.links.remove(link)

    mat.node_tree.links.new(mapping_node.outputs["Vector"], emb_tex_node.inputs["Vector"])


def enhance_toon_unif_env_settings(mat):
    if not mat: return
    mat.blend_method = 'BLEND'
    mat.show_transparent_back = False
    mat.use_backface_culling = False


def set_toon_unif_env_properties(mat, is_toon_unif_env):
    if not mat or not mat.node_tree: return
    group_node = mat.node_tree.nodes.get("Group")
    if group_node and "Is TOON_UNIF_ENV" in group_node.inputs:
        group_node.inputs["Is TOON_UNIF_ENV"].default_value = 1.0 if is_toon_unif_env else 0.0
        if is_toon_unif_env: print(f"[XV2] Enabled TOON_UNIF_ENV mode for material '{mat.name}'")


class XV2_Prefs(AddonPreferences):
    bl_idname = __name__
    emm_dir: StringProperty(name="EMM XML folder", subtype='DIR_PATH',
                            description="Folder containing EMM XML definition files")
    tex_dir: StringProperty(name="Texture folder", subtype='DIR_PATH',
                            description="Root folder for game textures (DDS, PNG, etc.)")

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "emm_dir")
        layout.prop(self, "tex_dir")


EXTS = (".dds", ".png", ".tga", ".jpg", ".jpeg")


def strip_num(n): return re.sub(r"\.\d+$", "", n).lower()


def find_image(primary_stub, original_material_name_hint, kind, tex_root, mat_scale1x_val=None):
    primary_stub = primary_stub.lower()
    original_material_name_hint = original_material_name_hint.lower()
    kind_lower = kind.lower()
    actual_search_suffixes = [kind_lower]
    patterns = []
    match_dot_num = re.match(r"(.+)\.(\d+)$", original_material_name_hint)
    if match_dot_num:
        base_from_dot, num_from_dot = match_dot_num.group(1), match_dot_num.group(2).zfill(3)
        if primary_stub == base_from_dot: patterns.append(f"{base_from_dot}_{num_from_dot}_{kind_lower}")
    patterns.append(f"{primary_stub}_{kind_lower}")
    if not re.search(r"_\d{3}$", primary_stub) and not match_dot_num:
        for i in range(10): patterns.append(f"{primary_stub}_{str(i).zfill(3)}_{kind_lower}")
    match_stub_variant = re.match(r"(.+)_(\d{3})$", primary_stub)
    if match_stub_variant:
        base_from_stub, num_from_stub = match_stub_variant.group(1), match_stub_variant.group(2)
        patterns.append(f"{base_from_stub}_{num_from_stub}_{kind_lower}")
        patterns.append(f"{base_from_stub}_{kind_lower}")
    unique_patterns = []
    for p in patterns:
        if p and p not in unique_patterns: unique_patterns.append(p)
    for pat in unique_patterns:
        for img in bpy.data.images:
            img_filepath_base_lower = ""
            if img.filepath: img_filepath_base_lower = \
                os.path.splitext(os.path.basename(bpy.path.abspath(img.filepath)))[0].lower()
            img_name_no_ext_lower = os.path.splitext(img.name)[0].lower()
            if img_filepath_base_lower.startswith(pat) or img_name_no_ext_lower.startswith(pat): return img
    if tex_root and os.path.isdir(tex_root):
        for pat in unique_patterns:
            for r, _, fs in os.walk(tex_root):
                for f_walk in fs:
                    f_walk_lower = f_walk.lower()
                    f_walk_base_lower = os.path.splitext(f_walk_lower)[0]
                    if f_walk_base_lower.startswith(pat) and f_walk_lower.endswith(EXTS):
                        try:
                            return bpy.data.images.load(os.path.join(r, f_walk), check_existing=True)
                        except RuntimeError as e:
                            print(f"[XV2] Warning: Could not load image: {os.path.join(r, f_walk)} - {e}")
    return None


def get_material_texture_nodes(mat):
    if not mat or not mat.node_tree: return None, None, None
    dyt_node = mat.node_tree.nodes.get("Image Texture.004")
    emb_lines_node = mat.node_tree.nodes.get("Image Texture.001")
    dual_emb_node = mat.node_tree.nodes.get("Image Texture Dual EMB")  # This is the mask texture node
    return dyt_node, emb_lines_node, dual_emb_node


def assign_images(mat, primary_stub, original_material_name, tex_root, shader_type="", mat_scale1x_val=None):
    """ONLY CHANGE: Remove MSK strength logic, add MSK invert setup"""
    if not mat:
        return

    dyt_node, emb_lines_node, dual_emb_node = get_material_texture_nodes(mat)

    if not (dyt_node and emb_lines_node and dual_emb_node):
        print(f"[XV2] Warn: Missing core texture nodes in '{mat.name}'. Skipping assignment.")
        return

    print(f"[XV2] PROCESSING: {mat.name} (stub: {primary_stub}, shader: {shader_type})")

    is_msk_shader = shader_type and "MSK" in shader_type.upper()
    is_xvm_shader = shader_type and "XVM" in shader_type.upper()

    # Find all textures (UNCHANGED)
    img_dyt = find_image(primary_stub, original_material_name, "dyt", tex_root, mat_scale1x_val)
    img_000 = find_image(primary_stub, original_material_name, "000", tex_root, mat_scale1x_val)
    img_001 = find_image(primary_stub, original_material_name, "001", tex_root, mat_scale1x_val)
    img_002 = find_image(primary_stub, original_material_name, "002", tex_root, mat_scale1x_val)

    # Texture assignment (UNCHANGED)
    if img_dyt:
        dyt_node.image = img_dyt
        print(f"[XV2] DYT: {img_dyt.name}")
    else:
        dyt_node.image = None

    if img_000:
        emb_lines_node.image = img_000
        print(f"[XV2] EMB Lines (000): {img_000.name}")
    elif not is_msk_shader and img_001:
        emb_lines_node.image = img_001
        print(f"[XV2] EMB Lines (000 fallback to 001): {img_001.name}")
    else:
        emb_lines_node.image = None
        print(f"[XV2] EMB Lines (000): NONE")

    # Mask assignment (UNCHANGED)
    assigned_mask_texture = None
    if is_xvm_shader:
        if img_002:
            assigned_mask_texture = img_002
            print(f"[XV2] Mask Texture (XVM Primary): {img_002.name} (_002)")
        elif img_001:
            assigned_mask_texture = img_001
            print(f"[XV2] Mask Texture (XVM Fallback): {img_001.name} (_001)")
    elif is_msk_shader:
        if img_001:
            assigned_mask_texture = img_001
            print(f"[XV2] Mask Texture (MSK): {img_001.name} (_001)")

    if assigned_mask_texture:
        dual_emb_node.image = assigned_mask_texture
    else:
        dual_emb_node.image = None
        print(f"[XV2] Mask Texture (MSK/XVM): No suitable texture found or shader type not requiring it.")

    # SIMPLIFIED shader flags - MSK now just sets up invert + XVM
    group_node = mat.node_tree.nodes.get("Group")
    if group_node:
        # Reset flags
        if "Is XVM" in group_node.inputs:
            group_node.inputs["Is XVM"].default_value = 0.0
        if "Dual EMB Strength" in group_node.inputs:
            group_node.inputs["Dual EMB Strength"].default_value = 1.0

        # MSK: Setup invert and enable XVM
        if is_msk_shader and dual_emb_node.image:
            setup_msk_as_inverted_xvm(mat, shader_type)

        # XVM: Enable directly
        elif is_xvm_shader and dual_emb_node.image:
            group_node.inputs["Is XVM"].default_value = 1.0
            print(f"    XVM System: ENABLED")
    else:
        print(f"[XV2] Warn: Main shader group node not found in '{mat.name}'. Cannot set flags.")


def set_dyt_line(mat, val):
    if not mat or not mat.node_tree: return
    dyt_control_node_instance = mat.node_tree.nodes.get("Group.002")
    if dyt_control_node_instance and dyt_control_node_instance.type == 'GROUP' and \
            dyt_control_node_instance.node_tree and dyt_control_node_instance.node_tree.name == "DYT Control [CAMERA BASED]" and \
            "DYT Line" in dyt_control_node_instance.inputs:
        dyt_control_node_instance.inputs["DYT Line"].default_value = val


def create_xv2_material(material_name="Xenoverse 2 - Dimps"):
    # Ensure node groups are up-to-date or created
    ensure_node_group("Xenoverse - Dimps.001", xenoverse___dimps_001_node_group_def)
    ensure_node_group("DYT Control [CAMERA BASED]", dyt_control__camera_based__node_group_def)

    mat = bpy.data.materials.get(material_name)
    if not mat:
        mat = bpy.data.materials.new(name=material_name)
    else:
        # Clear existing node tree to ensure fresh setup if material is reused
        if mat.node_tree:
            for node in list(mat.node_tree.nodes): mat.node_tree.nodes.remove(node)
            # bpy.data.node_trees.remove(mat.node_tree) # Could also remove tree itself
            # mat.node_tree = None

    mat.use_nodes = True
    if not mat.node_tree:
        mat.node_tree = bpy.data.node_trees.new(type='ShaderNodeTree', name=f"{material_name}_NT")

    xenoverse_2___dimps_node_group(mat.node_tree)  # This populates the material's node tree
    return mat


class XV2_OT_apply(Operator):
    bl_idname = "xv2.apply_shader"
    bl_label = "Apply/Update Shaders"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, ctx):
        prefs = ctx.preferences.addons[__name__].preferences
        if not prefs.emm_dir or not os.path.isdir(prefs.emm_dir): self.report({'WARNING'},
                                                                              "EMM folder not set/invalid.")
        rows, shader_types = build_row_map(prefs.emm_dir)
        ensure_eye_node_groups()  # ← ADDED THIS LINE
        clones = {}
        slots_assigned = 0
        processed_original_material_names = set()
        target_objects = [o for o in ctx.selected_objects if o.type == 'MESH'] or [o for o in bpy.data.objects if
                                                                                   o.type == 'MESH']
        if not target_objects: self.report({'WARNING'}, "No mesh objects to process."); return {'CANCELLED'}
        action_msg = "selected" if ctx.selected_objects else "all scene"
        print(f"[XV2] Processing {len(target_objects)} {action_msg} mesh object(s).")

        for obj in target_objects:
            if not obj.data or not obj.material_slots: continue
            original_material_info = []
            for i, slot in enumerate(obj.material_slots):
                if slot.material:
                    original_material_info.append((i, slot.material.name))
                    processed_original_material_names.add(slot.material.name)
                else:
                    original_material_info.append((i, None))

            for slot_index, original_name in original_material_info:
                if original_name is None:
                    if slot_index < len(obj.material_slots): obj.material_slots[slot_index].material = None
                    continue
                primary_stub = strip_num(original_name)
                cloned_mat = clones.get(primary_stub)
                if cloned_mat is None:
                    mat_scale1x = rows.get(primary_stub.lower())
                    if mat_scale1x is None and "_" in primary_stub:
                        parts = primary_stub.split('_')
                        if len(parts) > 2 and parts[-2].isdigit():
                            potential_base = "_".join(parts[:-2] + [parts[-1]])
                            if potential_base.lower() in rows: mat_scale1x = rows[potential_base.lower()]

                    shader_type_key = primary_stub.lower()
                    if shader_type_key not in shader_types and original_name.lower() in shader_types:
                        shader_type_key = original_name.lower()

                    shader_type = shader_types.get(shader_type_key, "")

                    # REPLACED material creation call
                    cloned_mat = create_xv2_material_enhanced(
                        material_name=primary_stub,
                        shader_type=shader_type,
                        primary_stub=primary_stub,
                        rows=rows,
                        texture_folder=prefs.tex_dir
                    )
                    if cloned_mat is None: continue

                    # REPLACED image assignment call
                    assign_images_enhanced_with_data_scan(cloned_mat, primary_stub, original_name, prefs.tex_dir, shader_type, mat_scale1x)

                    # This block is for the MAIN shader, not the EYE shader.
                    if not is_eye_shader(shader_type):
                        setup_dual_emb_color(cloned_mat, shader_type)

                        dyt_val = None
                        if mat_scale1x is not None: dyt_val = (mat_scale1x + 1) * 0.1
                        epsilon = 0.00001
                        if dyt_val is not None:
                            if dyt_val >= (0.6 - epsilon):
                                original_dyt_for_log = dyt_val;
                                dyt_val += 0.02
                                print(
                                    f"[XV2] Adjusting DYT Line for '{primary_stub}' (>=0.6 rule): {original_dyt_for_log:.3f} -> {dyt_val:.3f}")
                        if dyt_val is not None: set_dyt_line(cloned_mat, dyt_val)

                        is_toon_unif = shader_type == "TOON_UNIF_ENV"
                        set_toon_unif_env_properties(cloned_mat, is_toon_unif)
                        if is_toon_unif:
                            emb_tex_node = cloned_mat.node_tree.nodes.get("Image Texture.001")
                            shader_grp_node = cloned_mat.node_tree.nodes.get("Group")
                            if emb_tex_node and shader_grp_node and "EMB Alpha" in shader_grp_node.inputs:
                                emb_alpha_input = shader_grp_node.inputs["EMB Alpha"]
                                for link in list(cloned_mat.node_tree.links):
                                    if link.to_node == shader_grp_node and link.to_socket == emb_alpha_input and \
                                            link.from_node == emb_tex_node and link.from_socket == emb_tex_node.outputs[
                                        "Alpha"]:
                                        cloned_mat.node_tree.links.remove(link)
                                        print(
                                            f"[XV2] Auto-disconnected EMB Alpha for TOON_UNIF_ENV material: '{primary_stub}'")
                                        break
                            setup_toon_unif_env_camera_uvs(cloned_mat)
                            enhance_toon_unif_env_settings(cloned_mat)

                    clones[primary_stub] = cloned_mat

                if slot_index < len(obj.material_slots) and \
                        (obj.material_slots[slot_index].material is None or obj.material_slots[
                            slot_index].material.name != cloned_mat.name):
                    obj.material_slots[slot_index].material = cloned_mat;
                    slots_assigned += 1

        mats_to_remove = []
        for name_orig in processed_original_material_names:
            if name_orig and strip_num(name_orig) not in clones:
                mat_data = bpy.data.materials.get(name_orig)
                if mat_data and mat_data.users == 0 and not mat_data.use_fake_user: mats_to_remove.append(mat_data)

        if mats_to_remove:
            print(f"[XV2] Removing {len(mats_to_remove)} unused original materials:")
            for m_rem in mats_to_remove: print(f"  - '{m_rem.name}'"); bpy.data.materials.remove(m_rem)

        self.report({'INFO'},
                    f"XV2: Processed. {slots_assigned} slots updated. {len(clones)} unique shaders created/updated.")
        return {'FINISHED'}


def get_dyt_image_and_line_from_material(mat):
    if not mat or not mat.use_nodes or not mat.node_tree: return None, None
    dyt_img, dyt_line = None, None
    for node in mat.node_tree.nodes:
        if node.type == 'TEX_IMAGE' and node.image:
            img = node.image;
            fp_abs = bpy.path.abspath(img.filepath) if img.filepath else ""
            name_on_disk_lower = os.path.basename(fp_abs).lower() if fp_abs else ""
            name_in_blender_lower = img.name.lower()
            if "_dyt" in name_on_disk_lower or "_dyt" in name_in_blender_lower:
                is_main_dyt_tex = False
                if node.name == "Image Texture.004":
                    is_main_dyt_tex = True
                else:
                    main_shader_group = mat.node_tree.nodes.get("Group")
                    if main_shader_group:
                        for link in mat.node_tree.links:
                            if link.from_node == node and link.to_node == main_shader_group and link.to_socket == main_shader_group.inputs.get(
                                    "DYT"):
                                is_main_dyt_tex = True;
                                break
                if is_main_dyt_tex: dyt_img = img; break
    dyt_control_node = mat.node_tree.nodes.get("Group.002")
    if dyt_control_node and dyt_control_node.type == 'GROUP' and dyt_control_node.node_tree and dyt_control_node.node_tree.name == "DYT Control [CAMERA BASED]" and "DYT Line" in dyt_control_node.inputs:
        dyt_line = dyt_control_node.inputs["DYT Line"].default_value
    else:
        for node in mat.node_tree.nodes:
            if node.type == 'GROUP' and node.node_tree and node.node_tree.name == "DYT Control [CAMERA BASED]" and "DYT Line" in node.inputs:
                dyt_line = node.inputs["DYT Line"].default_value;
                break
    return dyt_img, dyt_line

class XV2_OT_copy_dyt_settings(Operator):
    bl_idname = "xv2.copy_dyt_settings"
    bl_label = "Copy DYT Settings"
    bl_description = "Copy DYT image and line value from active object's first material"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH'

    def execute(self, context):
        global _copied_dyt_image, _copied_dyt_line

        active_obj = context.active_object
        if not active_obj or not active_obj.material_slots:
            self.report({'WARNING'}, "Active object has no materials.")
            return {'CANCELLED'}

        # Get first material
        first_mat = None
        for slot in active_obj.material_slots:
            if slot.material:
                first_mat = slot.material
                break

        if not first_mat:
            self.report({'WARNING'}, "Active object has no assigned materials.")
            return {'CANCELLED'}

        # Get DYT settings
        dyt_img, dyt_line = get_dyt_image_and_line_from_material(first_mat)

        if dyt_img is None or dyt_line is None:
            self.report({'WARNING'}, f"Material '{first_mat.name}' has no DYT setup.")
            return {'CANCELLED'}

        # Store globally
        _copied_dyt_image = dyt_img
        _copied_dyt_line = dyt_line

        self.report({'INFO'},
                    f"Copied DYT settings from '{first_mat.name}' (DYT: {dyt_img.name}, Line: {dyt_line:.3f})")
        return {'FINISHED'}


class XV2_OT_paste_dyt_settings(Operator):
    bl_idname = "xv2.paste_dyt_settings"
    bl_label = "Paste DYT Settings"
    bl_description = "Paste copied DYT settings to all materials on selected objects"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        global _copied_dyt_image, _copied_dyt_line
        return context.selected_objects and _copied_dyt_image is not None and _copied_dyt_line is not None

    def execute(self, context):
        global _copied_dyt_image, _copied_dyt_line

        if _copied_dyt_image is None or _copied_dyt_line is None:
            self.report({'WARNING'}, "No DYT settings copied. Use 'Copy DYT Settings' first.")
            return {'CANCELLED'}

        target_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not target_objects:
            self.report({'WARNING'}, "No mesh objects selected.")
            return {'CANCELLED'}

        materials_updated = 0

        for obj in target_objects:
            if not obj.material_slots:
                continue

            for slot in obj.material_slots:
                if not slot.material:
                    continue

                mat = slot.material
                if not mat.use_nodes or not mat.node_tree:
                    continue

                # Find DYT nodes
                dyt_img_node = mat.node_tree.nodes.get("Image Texture.004")
                dyt_ctrl_node = mat.node_tree.nodes.get("Group.002")

                # Check if this looks like an XV2 material
                main_group = mat.node_tree.nodes.get("Group")
                if not main_group or main_group.type != 'GROUP':
                    continue

                success = False

                # Update DYT image
                if dyt_img_node and dyt_img_node.type == 'TEX_IMAGE':
                    dyt_img_node.image = _copied_dyt_image
                    success = True

                # Update DYT line
                if dyt_ctrl_node and dyt_ctrl_node.type == 'GROUP' and "DYT Line" in dyt_ctrl_node.inputs:
                    dyt_ctrl_node.inputs["DYT Line"].default_value = _copied_dyt_line
                    success = True

                if success:
                    materials_updated += 1
                    print(f"[XV2] Updated DYT settings for material: {mat.name}")

        if materials_updated > 0:
            self.report({'INFO'}, f"Applied DYT settings to {materials_updated} materials.")
        else:
            self.report({'WARNING'}, "No compatible materials found to update.")

        return {'FINISHED'}


class XV2_OT_disconnect_emb_alpha(Operator):
    bl_idname = "xv2.disconnect_emb_alpha"
    bl_label = "Disconnect EMB Alpha"
    bl_description = "Disconnect EMB Alpha input on materials from selected objects to fix black materials"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(obj.type == 'MESH' for obj in context.selected_objects)

    def execute(self, context):
        target_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not target_objects:
            self.report({'WARNING'}, "No mesh objects selected.")
            return {'CANCELLED'}

        processed_count = 0

        for obj in target_objects:
            if not obj.material_slots:
                continue

            for slot in obj.material_slots:
                if not slot.material:
                    continue

                mat = slot.material
                if not mat.use_nodes or not mat.node_tree:
                    continue

                # Find the main shader group and EMB texture node
                main_shader_group = mat.node_tree.nodes.get("Group")
                emb_texture_node = mat.node_tree.nodes.get("Image Texture.001")

                if not main_shader_group or main_shader_group.type != 'GROUP':
                    continue

                if "EMB Alpha" not in main_shader_group.inputs or not emb_texture_node or emb_texture_node.type != 'TEX_IMAGE':
                    continue

                # Find and remove the EMB Alpha connection
                emb_alpha_input_socket = main_shader_group.inputs["EMB Alpha"]
                for link in list(mat.node_tree.links):
                    if (link.to_node == main_shader_group and
                            link.to_socket == emb_alpha_input_socket and
                            link.from_node == emb_texture_node and
                            link.from_socket == emb_texture_node.outputs["Alpha"]):
                        mat.node_tree.links.remove(link)
                        print(f"[XV2] Disconnected EMB Alpha for material: '{mat.name}'")
                        processed_count += 1
                        break

        if processed_count > 0:
            self.report({'INFO'}, f"Disconnected EMB Alpha for {processed_count} materials.")
        else:
            self.report({'INFO'}, "No EMB Alpha connections found to disconnect.")

        return {'FINISHED'}


class XV2_PT_Main(Panel):
    bl_space_type, bl_region_type, bl_category = 'VIEW_3D', 'UI', "XV2";
    bl_label = "XV2 Auto-Shader"

    def draw(self, ctx):
        prefs = ctx.preferences.addons[__name__].preferences;
        layout = self.layout
        box_setup = layout.box();
        col_setup = box_setup.column(align=True);
        col_setup.label(text="Setup Paths:", icon='SETTINGS');
        col_setup.prop(prefs, "emm_dir", text="EMM Folder");
        col_setup.prop(prefs, "tex_dir", text="Texture Folder")
        box_actions = layout.box();
        col_actions = box_actions.column(align=True);
        col_actions.label(text="Main Actions:", icon='PLAY');
        col_actions.operator("xv2.apply_shader", text="Apply/Update Shaders", icon='SHADING_TEXTURE');
        col_actions.label(text="(If nothing selected, applies to all meshes)")
        box_notes = layout.box();
        col_notes = box_notes.column(align=True);
        col_notes.label(text="Info & Credits:", icon='INFO');
        col_notes.label(text="- Shader by Starr, Imxiater.");  # Updated
        col_notes.label(text="- Addon automation by Imxiater.")


def is_likely_broken_dxt1_dds(filepath):
    try:
        with open(filepath, "rb") as f:
            header = f.read(128)
        if len(header) < 128 or header[0:4] != b"DDS ": return False
        if header[84:88] != b"DXT1": return False
        flags = struct.unpack_from("<I", header, 8)[0];
        mipcount = struct.unpack_from("<I", header, 28)[0]
        return not (flags == 0x00001007 and mipcount == 0)
    except Exception as e:
        print(f"[XV2][DYT Fix] Error checking DDS header for '{filepath}': {e}");
        return False


def patch_dxt1_header_to_bytes(original_bytes):
    if len(original_bytes) < 128 or original_bytes[0:4] != b"DDS ": return original_bytes
    header = bytearray(original_bytes[:128])
    struct.pack_into("<I", header, 8, 0x00001007);
    struct.pack_into("<I", header, 20, 0);
    struct.pack_into("<I", header, 28, 0);
    struct.pack_into("<I", header, 88, 0)
    return bytes(header) + original_bytes[128:]


def create_fixed_image_from_path(original_path, new_name_base):
    try:
        with open(original_path, "rb") as f:
            data = f.read()
        patched_data = patch_dxt1_header_to_bytes(data)
        if patched_data == data: return None
        new_blender_image_name = bpy.path.display_name_from_filepath(new_name_base);
        final_name = new_blender_image_name;
        counter = 0
        while bpy.data.images.get(final_name) or bpy.data.images.get(
                f"{final_name}.000"): counter += 1; final_name = f"{new_blender_image_name}.{str(counter).zfill(3)}"
        tmp_file_path = ""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".dds") as tmp_f:
            tmp_file_path = tmp_f.name;
            tmp_f.write(patched_data)
        img = None
        try:
            img = bpy.data.images.load(tmp_file_path, check_existing=False);
            img.name = final_name;
            img.pack();
            img.filepath = "";
            img.filepath_raw = ""
        finally:
            if os.path.exists(tmp_file_path):
                try:
                    os.remove(tmp_file_path)
                except PermissionError:
                    print(f"[XV2][DYT Fix] Warning: Could not delete temp file '{tmp_file_path}' (permission error).")
                except Exception as e_del:
                    print(f"[XV2][DYT Fix] Warning: Could not delete temp file '{tmp_file_path}': {e_del}")
        return img
    except Exception as e_read:
        print(f"[XV2][DYT Fix] Failed to read/process image '{original_path}': {e_read}");
        return None


class XV2_OT_dyt_fix(Operator):
    bl_idname = "xv2.dyt_fix";
    bl_label = "Fix Invisible DYT DDS"
    bl_description = "Scans for malformed DXT1 DYT DDS. Creates fixed, packed copies. Does not alter originals.";
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        fixed_count, skipped_count, error_count = 0, 0, 0;
        processed_images = {}
        for mat in bpy.data.materials:
            if not mat or not mat.use_nodes or not mat.node_tree: continue
            for node in mat.node_tree.nodes:
                if node.type != 'TEX_IMAGE' or not node.image or not node.image.filepath: continue
                img = node.image;
                orig_path = bpy.path.abspath(img.filepath);
                base_name_lower = os.path.basename(orig_path).lower()
                is_dyt_file = (base_name_lower.endswith("_dyt.dds") or
                               (base_name_lower.startswith("data") and base_name_lower.endswith(".dds")))
                if not is_dyt_file: continue
                if orig_path in processed_images:
                    if processed_images[orig_path]:
                        if node.image != processed_images[orig_path]:
                            node.image = processed_images[orig_path];
                            fixed_count += 1
                        else:
                            skipped_count += 1
                    else:
                        skipped_count += 1
                    continue
                if not is_likely_broken_dxt1_dds(orig_path): skipped_count += 1; processed_images[
                    orig_path] = None; continue
                name_no_ext = os.path.splitext(os.path.basename(orig_path))[0];
                new_img_base_name = f"{name_no_ext}_fixed"
                new_fixed_img = create_fixed_image_from_path(orig_path, new_img_base_name)
                if new_fixed_img:
                    node.image = new_fixed_img;
                    processed_images[orig_path] = new_fixed_img;
                    fixed_count += 1;
                    print(
                        f"[XV2][DYT Fix] Fixed '{base_name_lower}' in '{mat.name}' to '{new_fixed_img.name}'.")
                else:
                    error_count += 1;
                    processed_images[orig_path] = None
        if fixed_count > 0:
            self.report({'INFO'}, f"DYT Fix: {fixed_count} fixed, {error_count} errors, {skipped_count} skipped.")
        elif error_count > 0:
            self.report({'WARNING'}, f"DYT Fix: {error_count} errors. {skipped_count} skipped.")
        elif skipped_count > 0 and fixed_count == 0 and error_count == 0:
            self.report({'INFO'}, f"DYT Fix: No malformed DYTs or all were already fixed. {skipped_count} skipped.")
        else:
            self.report({'INFO'}, "DYT Fix: No applicable DYT DDS files found.")
        return {'FINISHED'}


class XV2_PT_material_utilities_panel(Panel):
    bl_label = "Material Utilities"
    bl_idname = "XV2_PT_MATERIAL_UTILITIES"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'XV2'

    def draw(self, context):
        global _copied_dyt_image, _copied_dyt_line

        layout = self.layout

        # DYT Fix
        box_dyt_fix = layout.box()
        col_dyt_fix = box_dyt_fix.column(align=True)
        col_dyt_fix.label(text="Invisible DYT DDS Fix:", icon='FILE_IMAGE')
        col_dyt_fix.operator("xv2.dyt_fix", text="Scan & Fix DYTs", icon='TOOL_SETTINGS')
        col_dyt_fix.label(text="(Fixes common DXT1 header issues)")

        # DYT Copy/Paste
        box_dyt_copy = layout.box()
        col_dyt_copy = box_dyt_copy.column(align=True)
        col_dyt_copy.label(text="DYT Settings Transfer:", icon='EYEDROPPER')

        row = col_dyt_copy.row(align=True)
        row.operator("xv2.copy_dyt_settings", text="Copy DYT", icon='COPYDOWN')
        row.operator("xv2.paste_dyt_settings", text="Paste DYT", icon='PASTEDOWN')

        # Show what's currently copied
        if _copied_dyt_image is not None and _copied_dyt_line is not None:
            col_dyt_copy.label(text=f"Copied: {_copied_dyt_image.name}, Line: {_copied_dyt_line:.3f}", icon='INFO')
        else:
            col_dyt_copy.label(text="Nothing copied", icon='INFO')

        col_dyt_copy.label(text="Select source → Copy → Select targets → Paste")

        # EMB Alpha Fix
        box_alpha_fix = layout.box()
        col_alpha_fix = box_alpha_fix.column(align=True)
        col_alpha_fix.label(text="Fix Black Materials:", icon='CANCEL')
        col_alpha_fix.operator("xv2.disconnect_emb_alpha", text="Disconnect EMB Alpha", icon='UNLINKED')
        col_alpha_fix.label(text="(Works on all materials from selected objects)")


classes = (XV2_Prefs, XV2_OT_apply, XV2_PT_Main, XV2_OT_dyt_fix, XV2_PT_material_utilities_panel,
           XV2_OT_copy_dyt_settings, XV2_OT_paste_dyt_settings, XV2_OT_disconnect_emb_alpha,
           XV2_OT_set_dyt_transformation, XV2_PT_transformation_panel)

def register():
    for cls in classes: bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    try:
        unregister()
    except Exception:
        pass
    register()
    print("[XV2] Auto-Shader v4.5.0")