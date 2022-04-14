import gpu
from gpu.types import GPUShader

from functools import cache

class Shaders:

    @staticmethod
    @cache
    def uniform_color_2d():
        return gpu.shader.from_builtin("2D_UNIFORM_COLOR")


    @staticmethod
    @cache
    def uniform_color_3d():
        return gpu.shader.from_builtin("3D_UNIFORM_COLOR")

    @staticmethod
    @cache
    def id_shader_3d():
        vertex_shader = """
            uniform mat4 ModelViewProjectionMatrix;
            in vec3 pos;

            void main()
            {
              gl_Position = ModelViewProjectionMatrix * vec4(pos, 1.0);
            }
        """

        fragment_shader = """
            uniform vec4 color;
            out vec4 fragColor;

            void main()
            {
              fragColor = color;
            }
        """
        return GPUShader(vertex_shader, fragment_shader)

