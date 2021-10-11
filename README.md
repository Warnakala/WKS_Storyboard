WKS_Storyboard
==============

**WKS_Storyboard** is an application template aimed to simplify creating a multi-shot storyboard/animatic in Blender, using both Grease Pencil strokes and regular 3D objects.

Available Functions
-------------------

1. **New Shot**: Create a new shot at current frame, or any subsequent one to ensure existing shot's duration is at least 1 second. This is also the first command to run to initialize a new file. The shot will be isolated on (see _Toggle Shot Isolate_) and its first Grease Pencil object set as active (hereinafter referred to as shot activation).
2. **Previous/Next Shot**: Jumping onto, and activate, the shot before or after current one.
3. **Toggle Shot Isolate**: Using Blender's [**Preview Range**](https://docs.blender.org/manual/en/latest/editors/graph_editor/introduction.html#graph-preview-range) feature, localize preview to current shot. Decision to limit frame range (**Timeline** area → **Playback** → **Limit to Frame Range**) is left to the user.
4. **Reparent Current Shot Objects**: Run this command after any object addition to current shot, for proper shot transition on playback. By default, new objects will be added to current shot's [collection](https://docs.blender.org/manual/en/latest/scene_layout/collections/collections.html) because the collection will be selected upon the shot's activation.
5. **Shot List**: The list of all shots in the scene, ordered by position in the timeline. Users are recommended to _rename_ and _change duration_ of each shot using this list, instead of doing it manually.

To-Do List
----------

1. Proper shot removal.
2. Moving shot's position relative to others in the shot list.
3. Panel view: simultaneous view of all shots in a grid layout.
