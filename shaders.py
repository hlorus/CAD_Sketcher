import gpu
from gpu.types import GPUShader

import sys

if sys.version_info >= (3, 9):
    from functools import cache
else:
    from functools import lru_cache

    cache = lru_cache(maxsize=None)


class Shaders:

    base_vertex_shader_3d = """
        uniform mat4 ModelViewProjectionMatrix;

        in vec3 pos;

        void main() {
           gl_Position = ModelViewProjectionMatrix * vec4(pos.xyz, 1.0f);
        }
    """
    base_fragment_shader_3d = """
        uniform vec4 color;
        uniform float dash_width = 10.0;
        uniform float dash_factor = 0.40;
        uniform vec2 Viewport;
        uniform bool dashed = false;

        noperspective in vec2 stipple_pos;
        flat in vec2 stipple_start;

        out vec4 fragColor;
        void main() {

            float aspect = Viewport.x/Viewport.y;
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

    @staticmethod
    @cache
    def uniform_color_3d():
        return gpu.shader.from_builtin("3D_UNIFORM_COLOR")

    @classmethod
    @cache
    def uniform_color_image_2d(cls):
        vertex_shader = """
            uniform mat4 ModelViewProjectionMatrix;

            in vec2 pos;
            in vec2 texCoord;
            out vec2 v_texCoord;

            void main()
            {
                gl_Position = (
                    ModelViewProjectionMatrix * vec4(pos.xy, 0.0f, 1.0f)
                );
                v_texCoord = texCoord;
            }
        """
        fragment_shader = """
            uniform vec4 color;
            uniform sampler2D image;
            in vec2 v_texCoord;
            out vec4 fragColor;

            void main()
            {
                fragColor = blender_srgb_to_framebuffer_space(
                    texture(image, v_texCoord) * color
                );
            }
        """
        return GPUShader(
            vertex_shader,
            fragment_shader,
        )

    @classmethod
    @cache
    def id_line_3d(cls):
        shader = cls.uniform_color_line_3d()
        return shader

    @classmethod
    @cache
    def uniform_color_line_3d(cls):
        geometry_shader = """
            layout(lines) in;
            layout(triangle_strip, max_vertices = 10) out;

            uniform mat4 ModelViewProjectionMatrix;
            uniform vec2 Viewport;
            uniform float thickness = float(0.1);

            /* We leverage hardware interpolation to compute distance along the line. */
            noperspective out vec2 stipple_pos; /* In screen space */
            flat out vec2 stipple_start;        /* In screen space */

            out vec2 mTexCoord;
            out float alpha;
            float aspect = Viewport.x/Viewport.y;
            vec2 pxVec = vec2(1.0/Viewport.x,1.0/Viewport.y);
            float minLength =  length(pxVec);
            vec2 get_line_width(vec2 normal, float width){
                vec2 offsetvec = vec2(normal * width);
                if (length(offsetvec) < minLength){
                    offsetvec = normalize(offsetvec);
                    offsetvec *= minLength;
                }
                return(offsetvec);
            }
            float get_line_alpha(vec2 normal, float width){
                vec2 offsetvec = vec2(normal * width);
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
                vec2 dir = normalize((ssp2 - ssp1) * Viewport.xy);
                vec2 normal = vec2(-dir[1], dir[0]);
                normal = normalize(normal);

                // get offset factor from normal and user input thickness
                vec2 offset = get_line_width(normal,width) / Viewport.xy;
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

                    vec4 stipple_base;
                    if (i < 2) {
                        stipple_base = vec4(ssp1*p1.w,p1.z,p1.w);
                    }
                    else {
                        stipple_base = vec4(ssp2*p2.w, p2.z, p2.w);
                    }
                    stipple_start = stipple_pos = Viewport * 0.5 * (stipple_base.xy / stipple_base.w);

                    EmitVertex();
                }
                EndPrimitive();
            }
        """

        return GPUShader(
            cls.base_vertex_shader_3d,
            cls.base_fragment_shader_3d,
            geocode=geometry_shader,
        )

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
                int r = int(int(floor(fragColor.r * 255.0f)) | int(floor(color.r * 255.0f)));
                int g = int(int(floor(fragColor.g * 255.0f)) | int(floor(color.g * 255.0f)));
                int b = int(int(floor(fragColor.b * 255.0f)) | int(floor(color.b * 255.0f)));
                int a = int(int(floor(fragColor.a * 255.0f)) | int(floor(color.a * 255.0f)));
                fragColor.r = float(r) / 255.0f;
                fragColor.g = float(g) / 255.0f;
                fragColor.b = float(b) / 255.0f;
                fragColor.a = float(a) / 255.0f;
            }
        """
        return GPUShader(vertex_shader, fragment_shader)

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
