import bpy

def test_shaders():
    # Grass material
    mat_grass = bpy.data.materials.new("Test_Grass")
    mat_grass.use_nodes = True
    tree = mat_grass.node_tree
    tree.nodes.clear()
    
    node_out = tree.nodes.new("ShaderNodeOutputMaterial")
    node_bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    node_noise = tree.nodes.new("ShaderNodeTexNoise")
    node_color = tree.nodes.new("ShaderNodeValToRGB") # ColorRamp
    node_bump = tree.nodes.new("ShaderNodeBump")
    node_coord = tree.nodes.new("ShaderNodeTexCoord")
    node_map = tree.nodes.new("ShaderNodeMapping")
    
    # Mapping
    tree.links.new(node_coord.outputs["Object"], node_map.inputs["Vector"])
    tree.links.new(node_map.outputs["Vector"], node_noise.inputs["Vector"])
    
    # Noise settings
    node_noise.inputs["Scale"].default_value = 18.0
    node_noise.inputs["Detail"].default_value = 6.0
    node_noise.inputs["Roughness"].default_value = 0.65
    
    # Color ramp for grass
    node_color.color_ramp.elements[0].position = 0.35
    node_color.color_ramp.elements[0].color = (0.16, 0.38, 0.08, 1.0) # deep green
    node_color.color_ramp.elements[1].position = 0.70
    node_color.color_ramp.elements[1].color = (0.32, 0.58, 0.15, 1.0) # vibrant spring green
    
    tree.links.new(node_noise.outputs["Fac"], node_color.inputs["Fac"])
    tree.links.new(node_color.outputs["Color"], node_bsdf.inputs["Base Color"])
    
    # Bump for grass blades
    node_bump.inputs["Strength"].default_value = 0.35
    node_bump.inputs["Distance"].default_value = 0.05
    tree.links.new(node_noise.outputs["Fac"], node_bump.inputs["Height"])
    tree.links.new(node_bump.outputs["Normal"], node_bsdf.inputs["Normal"])
    
    node_bsdf.inputs["Roughness"].default_value = 0.75
    tree.links.new(node_bsdf.outputs["BSDF"], node_out.inputs["Surface"])
    
    # Viewport display color (affects solid mode!)
    mat_grass.diffuse_color = (0.28, 0.54, 0.16, 1.0)
    
    print("Shader created successfully!")

test_shaders()

