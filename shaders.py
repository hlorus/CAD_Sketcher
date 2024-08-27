import gpu
from gpu.types import GPUShader, GPUShaderCreateInfo, GPUStageInterfaceInfo
from gpu.shader import create_from_info
from bpy import app

import sys


if sys.version_info >= (3, 9):
    from functools import cache
else:
    from functools import lru_cache

    cache = lru_cache(maxsize=None)


class Shaders:

    base_vertex_shader_3d = """
        void main() {
           gl_Position = ModelViewProjectionMatrix * vec4(pos.xyz, 1.0f);

           vec2 ssPos = vec2(gl_Position.xy / gl_Position.w);
           segment_start = stipple_pos = ssPos;
        }
    """
    base_fragment_shader_3d = """
        void main() {

            vec2 delta = stipple_pos - segment_start;
            vec2 stipple_start;
            if (abs(delta.x) > abs(delta.y)) {
                stipple_start.x = 0;
                float t = -segment_start.x / delta.x;
                stipple_start.y = segment_start.y + t * delta.y;
            }
            else {
                stipple_start.y = 0;
                float t = -segment_start.y / delta.y;
                stipple_start.x = segment_start.x + t * delta.x;
            }
            float distance_along_line = distance(stipple_pos, stipple_start);
            float normalized_distance = fract(distance_along_line / dash_width);

            if (dashed == true) {
                if (normalized_distance <= dash_factor) {
                    discard;
                }
                else {
                    fragColor = color;
                }
            }
            else {
                fragColor = color;
            }

        }
    """

    @classmethod
    def get_base_shader_3d_info(cls):

        vert_out = GPUStageInterfaceInfo("stipple_pos_interface")
        vert_out.no_perspective("VEC2", "stipple_pos")
        vert_out.flat("VEC2", "segment_start")

        # NOTE: How to set default values?

        shader_info = GPUShaderCreateInfo()
        shader_info.push_constant("MAT4", "ModelViewProjectionMatrix")
        shader_info.push_constant("VEC4", "color")
        shader_info.push_constant("FLOAT", "dash_width")
        shader_info.push_constant("FLOAT", "dash_factor")
        # shader_info.push_constant("VEC2", "Viewport")
        shader_info.push_constant("BOOL", "dashed")
        shader_info.vertex_in(0, "VEC3", "pos")
        shader_info.vertex_out(vert_out)
        shader_info.fragment_out(0, "VEC4", "fragColor")

        shader_info.vertex_source(cls.base_vertex_shader_3d)
        shader_info.fragment_source(cls.base_fragment_shader_3d)

        return shader_info

    @staticmethod
    @cache
    def uniform_color_3d():
        if app.version < (3, 5):
            return gpu.shader.from_builtin("3D_UNIFORM_COLOR")
        return gpu.shader.from_builtin("UNIFORM_COLOR")

    @classmethod
    @cache
    def uniform_color_image_2d(cls):
        vert_out = GPUStageInterfaceInfo("uniform_color_image_2d_interface")
        vert_out.smooth("VEC2", "v_texCoord")

        shader_info = GPUShaderCreateInfo()
        shader_info.define("blender_srgb_to_framebuffer_space(a)", "a")
        shader_info.push_constant("MAT4", "ModelViewProjectionMatrix")
        shader_info.push_constant("VEC4", "color")
        shader_info.vertex_in(0, "VEC2", "pos")
        shader_info.vertex_in(1, "VEC2", "texCoord")
        shader_info.sampler(0, "FLOAT_2D", "image")
        shader_info.vertex_out(vert_out)
        shader_info.fragment_out(0, "VEC4", "fragColor")

        shader_info.vertex_source(
            """
            void main()
            {
                gl_Position = (
                    ModelViewProjectionMatrix * vec4(pos.xy, 0.0f, 1.0f)
                );
                v_texCoord = texCoord;
            }
        """
        )
        shader_info.fragment_source(
            """
            void main()
            {
                fragColor = blender_srgb_to_framebuffer_space(
                    texture(image, v_texCoord) * color
                );
            }
        """
        )

        shader = create_from_info(shader_info)
        del vert_out
        del shader_info
        return shader

    @classmethod
    @cache
    def id_line_3d(cls):
        shader = cls.uniform_color_line_3d()
        return shader

    @classmethod
    @cache
    def uniform_color_line_3d(cls):

        shader_info = cls.get_base_shader_3d_info()
        shader = create_from_info(shader_info)
        del shader_info
        return shader

    @staticmethod
    @cache
    def id_shader_3d():
        shader_info = GPUShaderCreateInfo()
        shader_info.push_constant("MAT4", "ModelViewProjectionMatrix")
        shader_info.push_constant("VEC4", "color")
        shader_info.vertex_in(0, "VEC3", "pos")
        shader_info.fragment_out(0, "VEC4", "fragColor")

        shader_info.vertex_source(
        """
            void main()
            {
              gl_Position = ModelViewProjectionMatrix * vec4(pos, 1.0);
            }
        """
        )

        shader_info.fragment_source(
        """
            void main()
            {
              fragColor = color;
            }
        """
        )
        
        shader = create_from_info(shader_info)
        del shader_info
        return shader

    @staticmethod
    @cache
    def dashed_uniform_color_3d():
        vertex_shader = """
            uniform mat4 ModelViewProjectionMatrix;
            in vec3 pos;
            in float arcLength;

            out float v_ArcLength;
            vec4 project = ModelViewProjectionMatrix * vec4(pos, 1.0f);
            vec4 offset = vec4(0,0,-0.001,0);
            void main()
            {
                v_ArcLength = arcLength;
                gl_Position = project + offset;
            }
        """

        fragment_shader = """
            uniform float u_Scale;
            uniform vec4 color;

            in float v_ArcLength;
            out vec4 fragColor;

            void main()
            {
                if (step(sin(v_ArcLength * u_Scale), 0.7) == 0) discard;
                fragColor = color;
            }
        """
        return GPUShader(vertex_shader, fragment_shader)
