// {title}: a compiled moy cart (SPEC.md 16) drawn by Jet, CubeCoders' software
// 3D rasteriser (github.com/CubeCoders/Jet, MIT, in src/jet/). The scene is
// JetExamples' template-cube: a debug cube turning on three axes. Replace
// init_scene and update_scene with your own.
//
// Jet renders RGB565 into a buffer the cart owns, and blit565 hands that
// frame to the console whole (SPEC.md 16.5). The buttons turn the cube.
//
// `moy build` compiles src/ into main.wasm; `moy play` rebuilds it when you
// save a file here, and reloads it.
#include <cmath>

#include "Primitives.hpp"
#include "Scene.hpp"
#include "moy_cart.h"

extern "C" void __wasm_call_ctors(void);

namespace {

const int W = 320, H = 240;

// What blit565 takes: W x H RGB565 words, little-endian.
alignas(16) uint16_t frame[W * H];
alignas(16) uint16_t depth[ZBUFFER_STRIDE(W) * H];

Renderer::Scene *scene = nullptr;
Renderer::Camera camera;
Renderer::Object *mesh = nullptr;
float pitch = 20.0f, yaw = 30.0f, roll = 0.0f;

void init_scene(Renderer::Scene &s)
{
    camera.setPosition(0, 0, -550);
    camera.setRotation(0, 0, 0);
    camera.setFOV(60.0f, W);
    camera.nearPlane = 16;
    camera.farPlane = 2000;
    s.setCamera(&camera);
    s.setClearBuffer(true);
    s.setBackcolor(0x0841);
    mesh = Primitives::createDebugCube(200, 200, 200);
    mesh->setRotation(20, 30, 0);
    s.addObject(mesh);
}

void update_scene(float seconds)
{
    const float turn = 90.0f * seconds;
    yaw += turn * float(moy_btn(MOY_RIGHT, 0) - moy_btn(MOY_LEFT, 0));
    pitch += turn * float(moy_btn(MOY_DOWN, 0) - moy_btn(MOY_UP, 0));
    pitch = std::fmod(pitch + 23.0f * seconds + 360.0f, 360.0f);
    yaw = std::fmod(yaw + 37.0f * seconds + 360.0f, 360.0f);
    roll = std::fmod(roll + 11.0f * seconds, 360.0f);
    mesh->setRotation(int(pitch), int(yaw), int(roll));
}

}  // namespace

MOY_EXPORT("_init") void init()
{
    __wasm_call_ctors();
    scene = new Renderer::Scene(frame, depth, W, H);
    init_scene(*scene);
}

MOY_EXPORT("_update") void update(float dt) { update_scene(dt); }

MOY_EXPORT("_draw") void draw()
{
    scene->render();
    moy_blit565(frame);
    static const char hint[] = "arrows turn the cube";
    moy_print(hint, sizeof hint - 1, 8, 228, 7);
}
