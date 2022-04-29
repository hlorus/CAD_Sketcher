import gpu
from gpu.types import GPUShader

import sys
if sys.version_info >= (3, 9):
    from functools import cache
else:
    from functools import lru_cache
    cache = lru_cache(maxsize=None)

class Shaders:

    base_vertex_shader_3d = '''
        uniform mat4 ModelViewProjectionMatrix;

        in vec3 pos;
        vec4 project = ModelViewProjectionMatrix * vec4(pos, 1.0);
        void main() {
           gl_Position = project;
        }
    '''
    base_fragment_shader_3d = '''
        uniform vec4 color;

        out vec4 fragColor;
        void main() {
            fragColor = color;
        }
    '''

    @staticmethod
    @cache
    def uniform_color_2d():
        return gpu.shader.from_builtin("2D_UNIFORM_COLOR")


    @staticmethod
    @cache
    def uniform_color_3d():
        return gpu.shader.from_builtin("3D_UNIFORM_COLOR")

    @classmethod
    @cache
    def id_line_3d(cls):
        shader = cls.uniform_color_line_3d()
        return shader

    @classmethod
    @cache
    def uniform_color_line_3d(cls):
        geometry_shader = '''
            layout(lines) in;
            layout(triangle_strip, max_vertices = 10) out;

            uniform mat4 ModelViewProjectionMatrix;
            uniform vec2 Viewport;
            uniform float thickness = float(0.1);

            out vec2 mTexCoord;
            out float alpha;
            float aspect = Viewport.x/Viewport.y;
            vec2 pxVec = vec2(1.0/Viewport.x,1.0/Viewport.y);
            float minLength =  length(pxVec);
            vec2 get_line_width(vec2 normal, float width){
                vec2 offsetvec = vec2(normal * width);
                offsetvec.x /= Viewport.x;
                offsetvec.y /= Viewport.y;
                if (length(offsetvec) < minLength){
                    offsetvec = normalize(offsetvec);
                    offsetvec *= minLength;
                }
                return(offsetvec);
            }
            float get_line_alpha(vec2 normal, float width){
                vec2 offsetvec = vec2(normal * width);
                offsetvec.x /= Viewport.x;
                offsetvec.y /= Viewport.y;
                float alpha = 1.0;
                if (length(offsetvec) < minLength){
                    alpha *= (length(offsetvec)/minLength);
                }
                return alpha;
            }
            void main() {
                //calculate line normal
                vec4 p1 =  gl_in[0].gl_Position;
                vec4 p2 =  gl_in[1].gl_Position;
                vec2 ssp1 = vec2(p1.xy / p1.w);
                vec2 ssp2 = vec2(p2.xy / p2.w);
                float width = thickness;
                vec2 dir = normalize(ssp2 - ssp1);
                vec2 normal = vec2(-dir[1], dir[0]);
                normal = normalize(normal);

                // get offset factor from normal and user input thickness
                vec2 offset = get_line_width(normal,width);
                float lineAlpha = get_line_alpha(normal,width);
                vec4 coords[4];
                vec2 texCoords[4];
                coords[0] = vec4((ssp1 + offset)*p1.w,p1.z,p1.w);
                texCoords[0] = vec2(0,1);
                coords[1] = vec4((ssp1 - offset)*p1.w,p1.z,p1.w);
                texCoords[1] = vec2(0,0);
                coords[2] = vec4((ssp2 + offset)*p2.w,p2.z,p2.w);
                texCoords[2] = vec2(0,1);
                coords[3] = vec4((ssp2 - offset)*p2.w,p2.z,p2.w);
                texCoords[3] = vec2(0,0);

                for (int i = 0; i < 4; ++i) {
                    mTexCoord = texCoords[i];
                    gl_Position = coords[i];
                    alpha = lineAlpha;
                    EmitVertex();
                }
                EndPrimitive();
            }
        '''

        return GPUShader(cls.base_vertex_shader_3d, cls.base_fragment_shader_3d, geocode=geometry_shader, name="uniform_color_line_3d")


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
        return GPUShader(vertex_shader, fragment_shader, name="id_shader_3d")

    @staticmethod
    @cache
    def dashed_uniform_color_3d():
        vertex_shader = '''
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
        '''

        fragment_shader = '''
            uniform float u_Scale;
            uniform vec4 color;

            in float v_ArcLength;
            out vec4 fragColor;

            void main()
            {
                if (step(sin(v_ArcLength * u_Scale), 0.7) == 0) discard;
                fragColor = color;
            }
        '''
        return GPUShader(vertex_shader, fragment_shader, name="dashed_uniform_color_3d")
