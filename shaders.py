import gpu
from gpu.types import GPUShader, GPUShaderCreateInfo, GPUStageInterfaceInfo
from gpu.shader import create_from_info

import sys


if sys.version_info >= (3, 9):
    from functools import cache
else:
    from functools import lru_cache

    cache = lru_cache(maxsize=None)


class Shaders:

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

    @staticmethod
    @cache
    def id_shader_3d():
        """Simple ID shader for selection rendering (both points and lines)."""
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
