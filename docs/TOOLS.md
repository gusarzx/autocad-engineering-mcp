# MCP tools

85 registered tools. Generated from the actual server.

COM implementations require Windows verification. Mock evidence is separate.
All geometry is 2D XY; engineering axonometry is a flat projection.

| Tool | Description |
| --- | --- |
| `autocad_connect` | Attach to AutoCAD 2027. Starting a new process needs explicit allow_launch. |
| `autocad_disconnect` | Release COM references; leave AutoCAD and its drawings open. |
| `autocad_get_status` | Report backend and connection; never claim tested Windows compatibility. |
| `autocad_get_version` | Read the connected application's version. |
| `autocad_list_documents` | List open documents without closing or modifying them. |
| `autocad_get_active_document` | Read active drawing name, units, saved state and document identity. |
| `autocad_select_document` | Activate an already-open drawing by exact name. |
| `autocad_create_document` | Create a new document and explicitly set INSUNITS (default 4 = mm). |
| `autocad_open_document` | Open an existing DWG inside configured save_root. |
| `autocad_save_document` | Save active DWG with path policy and backup. Existing file requires overwrite=true. |
| `autocad_save_as` | Save an editable DWG inside save_root; default is dry-run. Mock cannot write DWG. |
| `cad_draw_line` | Create a 2D editable WCS line; points must have z=0. |
| `cad_draw_polyline` | Create a planar editable lightweight polyline. |
| `cad_draw_circle` | Create a 2D editable circle. |
| `cad_draw_arc` | Create a 2D arc; angles are radians, counterclockwise. |
| `cad_draw_text` | Create editable single-line text; rotation is radians. |
| `cad_draw_mtext` | Create editable multiline text. |
| `cad_draw_dimension` | Create editable aligned dimension on the given layer. |
| `cad_draw_spline` | Create a 2D fit-point spline with endpoint tangents from route. |
| `cad_draw_hatch` | Hatch a closed circle/polyline; first boundary outer, remaining holes. |
| `cad_create_layer` | Create a configured layer; existing layers are left unchanged. |
| `cad_create_block` | Create an original generic rectangle/cross schematic symbol. |
| `cad_insert_block` | Insert a defined block or 2D DWG library inside save_root. |
| `cad_draw_rectangle` | Draw a closed 2D rectangle as an editable lightweight polyline. |
| `cad_draw_polygon` | Draw a regular 2D polygon, with radius to its vertices. |
| `cad_execute_batch` | Creation-only batch with typed preflight and optional best-effort COM cleanup. |
| `cad_list_layers` | Read drawing layers and their editable drafting properties. |
| `cad_set_current_layer` | Set an existing current layer. |
| `cad_set_layer_color` | Set indexed colour; colours are project conventions, not mandated standards. |
| `cad_set_layer_linetype` | Use an already-loaded linetype; this tool does not execute commands to load files. |
| `cad_set_layer_lineweight` | Set a valid ActiveX lineweight enumerator (hundredths of mm, or default flags). |
| `cad_delete_layer` | Delete an unused, unprotected layer only with explicit confirm=true. |
| `cad_list_blocks` | List block definitions; model-space and paper-space layouts are excluded. |
| `cad_get_block_attributes` | Read editable block attribute tags/values by DWG handle. |
| `cad_set_block_attributes` | Update standard block tags; unknown tags are rejected. |
| `cad_get_entity_properties` | Read bounded standard properties, attributes and engineering XData. |
| `cad_get_entities` | Page model-space objects by returned next_offset; optional layer/type/MARK filters. |
| `cad_get_selected_entities` | Read the current Pickfirst preselection without prompting or selecting objects. |
| `cad_find_entities_by_layer` | Page model-space entities on a specific layer. |
| `cad_find_entities_by_type` | Page entities of type line/polyline/circle/arc/text/mtext/insert_block/dimension. |
| `cad_get_drawing_bounds` | Read regenerated model-space WCS extents; mock bounds are approximate. |
| `cad_get_document_units` | Read INSUNITS; geometry converts mm/cm/m/in/ft and rejects ambiguous unitless DWGs. |
| `cad_move` | 2D move; large changes require confirm=true, deletions always require it. Linked engineering geometry must be recreated instead of transformed. |
| `cad_copy` | 2D copy; large changes require confirm=true, deletions always require it. Linked engineering geometry must be recreated instead of transformed. |
| `cad_rotate` | 2D rotate; large changes require confirm=true, deletions always require it. Linked engineering geometry must be recreated instead of transformed. |
| `cad_scale` | 2D scale; large changes require confirm=true, deletions always require it. Linked engineering geometry must be recreated instead of transformed. |
| `cad_delete` | 2D delete; large changes require confirm=true, deletions always require it. Linked engineering geometry must be recreated instead of transformed. |
| `cad_offset` | 2D offset; large changes require confirm=true, deletions always require it. Linked engineering geometry must be recreated instead of transformed. |
| `cad_mirror` | 2D mirror; large changes require confirm=true, deletions always require it. Linked engineering geometry must be recreated instead of transformed. |
| `cad_delete_block_reference` | 2D delete_block_reference; large changes require confirm=true, deletions always require it. Linked engineering geometry must be recreated instead of transformed. |
| `hvac_create_system` | Declare a hvac system and create its configured 2D layers. |
| `plumbing_create_system` | Declare a plumbing system and create its configured 2D layers. |
| `hvac_draw_duct` | Draw a 2D centreline duct with section, airflow, elevation and persistent topology. |
| `plumbing_draw_pipe` | Draw a 2D pipe schematic. Logical XYZ is projected in axonometric mode; no 3D object. |
| `hvac_insert_fan` | Insert editable 2D fan block with MARK/NAME/TYPE/SIZE/SYSTEM attributes. |
| `hvac_insert_ahu` | Insert editable 2D ahu block with MARK/NAME/TYPE/SIZE/SYSTEM attributes. |
| `hvac_insert_diffuser` | Insert editable 2D diffuser block with MARK/NAME/TYPE/SIZE/SYSTEM attributes. |
| `hvac_insert_grille` | Insert editable 2D grille block with MARK/NAME/TYPE/SIZE/SYSTEM attributes. |
| `hvac_insert_damper` | Insert editable 2D damper block with MARK/NAME/TYPE/SIZE/SYSTEM attributes. |
| `hvac_insert_filter` | Insert editable 2D filter block with MARK/NAME/TYPE/SIZE/SYSTEM attributes. |
| `hvac_insert_heater` | Insert editable 2D heater block with MARK/NAME/TYPE/SIZE/SYSTEM attributes. |
| `hvac_insert_silencer` | Insert editable 2D silencer block with MARK/NAME/TYPE/SIZE/SYSTEM attributes. |
| `hvac_insert_pump` | Insert editable 2D pump block with MARK/NAME/TYPE/SIZE/SYSTEM attributes. |
| `hvac_insert_radiator` | Insert editable 2D radiator block with MARK/NAME/TYPE/SIZE/SYSTEM attributes. |
| `plumbing_insert_valve` | Insert editable 2D valve block with MARK/NAME/TYPE/SIZE/SYSTEM attributes. |
| `plumbing_insert_gate_valve` | Insert editable 2D gate_valve block with MARK/NAME/TYPE/SIZE/SYSTEM attributes. |
| `plumbing_insert_ball_valve` | Insert editable 2D ball_valve block with MARK/NAME/TYPE/SIZE/SYSTEM attributes. |
| `plumbing_insert_check_valve` | Insert editable 2D check_valve block with MARK/NAME/TYPE/SIZE/SYSTEM attributes. |
| `plumbing_insert_pump` | Insert editable 2D pump block with MARK/NAME/TYPE/SIZE/SYSTEM attributes. |
| `plumbing_insert_filter` | Insert editable 2D filter block with MARK/NAME/TYPE/SIZE/SYSTEM attributes. |
| `plumbing_insert_water_meter` | Insert editable 2D water_meter block with MARK/NAME/TYPE/SIZE/SYSTEM attributes. |
| `plumbing_insert_fixture` | Insert editable 2D fixture block with MARK/NAME/TYPE/SIZE/SYSTEM attributes. |
| `plumbing_insert_tee` | Insert editable 2D tee block with MARK/NAME/TYPE/SIZE/SYSTEM attributes. |
| `plumbing_insert_reducer` | Insert editable 2D reducer block with MARK/NAME/TYPE/SIZE/SYSTEM attributes. |
| `plumbing_insert_cleanout` | Insert editable 2D cleanout block with MARK/NAME/TYPE/SIZE/SYSTEM attributes. |
| `hvac_create_riser` | Draw a 2D riser circle and mark; elevation remains engineering metadata. |
| `plumbing_create_riser` | Draw a 2D riser circle and mark; elevation remains engineering metadata. |
| `hvac_label_duct` | Label equipment or route from current drawing metadata. |
| `hvac_label_equipment` | Label equipment or route from current drawing metadata. |
| `plumbing_label_pipe` | Label equipment or route from current drawing metadata. |
| `plumbing_label_equipment` | Label equipment or route from current drawing metadata. |
| `hvac_generate_specification` | Aggregate DWG XData routes/attributed blocks. Optional editable 2D text schedule. |
| `plumbing_generate_specification` | Aggregate DWG XData routes/attributed blocks. Optional editable 2D text schedule. |
| `cad_generate_specification` | Aggregate DWG XData routes/attributed blocks. Optional editable 2D text schedule. |
| `cad_get_engineering_network` | Read logical nodes/edges; connections require matching route vertices. |
