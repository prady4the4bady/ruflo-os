// SPDX-License-Identifier: MIT
/*
 * Ruflo Compositor - Weston-based Wayland compositor
 * Custom shell protocol for Ruflo desktop
 * Input event capture for AI agent
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wayland-server.h>
#include "ruflo-compositor.h"

static struct ruflo_server server = {0};

/* Output handling */
static void ruflo_output_destroy(struct wl_listener *listener, void *data) {
    struct ruflo_output *output = wl_container_of(listener, output, destroy);
    wl_list_remove(&output->link);
    wl_list_remove(&output->frame.link);
    wl_list_remove(&output->destroy.link);
    free(output);
}

static void ruflo_output_frame(struct wl_listener *listener, void *data) {
    struct ruflo_output *output = wl_container_of(listener, output, frame);
    struct wlr_output *wlr_output = output->wlr_output;

    struct wlr_renderer *renderer = wlr_backend_get_renderer(
        wlr_output->backend);

    if (!wlr_output->enabled) return;

    struct wlr_output_state state;
    wlr_output_state_init(&state);
    wlr_output_state_set_enabled(&state, true);

    if (!wlr_output_commit_state(wlr_output, &state)) {
        wlr_output_state_finish(&state);
        return;
    }
    wlr_output_state_finish(&state);
}

static void new_output(struct wl_listener *listener, void *data) {
    struct wlr_output *wlr_output = data;

    if (!wl_list_empty(&wlr_output->modes)) {
        struct wlr_output_mode *mode = wl_container_of(
            wlr_output->modes.prev, mode, link);
        wlr_output_set_mode(wlr_output, mode);
    }

    struct ruflo_output *output = calloc(1, sizeof(*output));
    output->server = &server;
    output->wlr_output = wlr_output;
    output->frame.notify = ruflo_output_frame;
    wl_signal_add(&wlr_output->events.frame, &output->frame);
    output->destroy.notify = ruflo_output_destroy;
    wl_signal_add(&wlr_output->events.destroy, &output->destroy);
    wl_list_insert(&server.outputs, &output->link);

    wlr_output_create_global(wlr_output);
}

/* Input handling - capture all events for AI */
static void keyboard_key_notify(struct wl_listener *listener, void *data) {
    struct wlr_keyboard_key_event *event = data;
    // Forward to AI Bridge kernel module
    int fd = open("/dev/ai_bridge", O_RDWR | O_NONBLOCK);
    if (fd >= 0) {
        // Write key event to kernel device
        close(fd);
    }
}

static void new_keyboard(struct wlr_input_device *device) {
    struct wlr_keyboard *kb = wlr_keyboard_from_input_device(device);
    wl_signal_add(&kb->events.key, &server.keyboard_key);
    // Add to keyboards list
}

static void new_pointer(struct wlr_input_device *device) {
    // Handle pointer for AI cursor overlay
}

static void new_input(struct wl_listener *listener, void *data) {
    struct wlr_input_device *device = data;
    switch (device->type) {
    case WLR_INPUT_DEVICE_KEYBOARD:
        new_keyboard(device);
        break;
    case WLR_INPUT_DEVICE_POINTER:
        new_pointer(device);
        break;
    default:
        break;
    }
}

/* XDG Shell handling */
static void new_xdg_surface(struct wl_listener *listener, void *data) {
    struct wlr_xdg_surface *xdg_surface = data;
    if (xdg_surface->role != WLR_XDG_SURFACE_ROLE_TOPLEVEL) return;

    struct ruflo_view *view = calloc(1, sizeof(*view));
    view->server = &server;
    view->xdg_surface = xdg_surface;
    view->surface = xdg_surface->surface;
    view->mapped = false;

    // Set up event handlers for map, unmap, destroy
    wl_signal_add(&xdg_surface->events.map, &view->map);
    wl_signal_add(&xdg_surface->events.unmap, &view->unmap);
    wl_signal_add(&xdg_surface->events.destroy, &view->destroy);

    wl_list_insert(&server.views, &view->link);
}

int main(int argc, char **argv) {
    wlr_log_init(WLR_DEBUG, NULL);

    server.display = wl_display_create();
    server.backend = wlr_backend_autocreate(server.display, NULL);
    server.renderer = wlr_backend_get_renderer(server.backend);
    wlr_renderer_init_wl_display(server.renderer, server.display);

    server.compositor = wlr_compositor_create(server.display, 5, server.renderer);
    server.output_layout = wlr_output_layout_create(server.display);

    server.xdg_shell = wlr_xdg_shell_create(server.display, 5);
    server.new_xdg_surface.notify = new_xdg_surface;
    wl_signal_add(&server.xdg_shell->events.new_surface, &server.new_xdg_surface);

    server.seat = wlr_seat_create(server.display, "seat0");

    // Input devices
    server.new_input.notify = new_input;
    wl_signal_add(&server.backend->events.new_input, &server.new_input);

    // Outputs
    server.new_output.notify = new_output;
    wl_signal_add(&server.backend->events.new_output, &server.new_output);

    // Initialize AI overlay layer
    // ...

    const char *socket = wl_display_add_socket_auto(server.display);
    if (!socket) {
        wlr_backend_destroy(server.backend);
        return 1;
    }

    if (!wlr_backend_start(server.backend)) {
        wlr_backend_destroy(server.backend);
        return 1;
    }

    wlr_log(WLR_INFO, "Ruflo Shell running on Wayland socket: %s", socket);
    wl_display_run(server.display);

    wl_display_destroy(server.display);
    return 0;
}
