// SPDX-License-Identifier: MIT
/*
 * ruflo-compositor.h - Header for Ruflo Wayland Compositor
 * Weston-based compositor with AI overlay support
 */
#ifndef RUFLO_COMPOSITOR_H
#define RUFLO_COMPOSITOR_H

#include <wayland-server.h>
#include <wlr/backend.h>
#include <wlr/render.h>
#include <wlr/types/wlr_compositor.h>
#include <wlr/types/wlr_data_device.h>
#include <wlr/types/wlr_input_device.h>
#include <wlr/types/wlr_keyboard.h>
#include <wlr/types/wlr_matrix.h>
#include <wlr/types/wlr_output.h>
#include <wlr/types/wlr_output_layout.h>
#include <wlr/types/wlr_pointer.h>
#include <wlr/types/wlr_seat.h>
#include <wlr/types/wlr_xcursor_manager.h>
#include <wlr/types/wlr_xdg_shell.h>
#include <wlr/types/wlr_layer_shell_v1.h>
#include <wlr/util/log.h>
#include <wlr/util/edges.h>

/* Ruflo Server Structure */
struct ruflo_server {
    struct wl_display *wl_display;
    struct wlr_backend *backend;
    struct wlr_renderer *renderer;
    struct wlr_compositor *compositor;
    struct wlr_output_layout *output_layout;
    struct wlr_xdg_shell *xdg_shell;
    struct wlr_layer_shell_v1 *layer_shell;
    struct wl_list outputs;
    struct wl_list keyboards;
    struct wl_list pointers;
    struct wl_list views;
    struct wlr_seat *seat;
    struct wlr_xcursor_manager *cursor_mgr;
    struct wlr_input_inhibit_manager *inhibit;
    struct wlr_idle *idle;
    struct wlr_idle_inhibit_manager *idle_inhibit;

    /* macOS-style features */
    struct wl_list spaces;  /* Virtual desktops */
    int current_space;
    struct wl_list animations; /* Window animations */

    /* AI Overlay */
    struct wlr_surface *ai_overlay; /* Transparent surface for agent cursor */
    bool ai_mode_active;
};

/* Ruflo Output */
struct ruflo_output {
    struct wl_list link;
    struct ruflo_server *server;
    struct wlr_output *wlr_output;
    struct wl_listener frame;
    struct wl_listener destroy;
};

/* Ruflo View (window) */
struct ruflo_view {
    struct wl_list link;
    struct ruflo_server *server;
    struct wlr_xdg_surface *xdg_surface;
    struct wlr_surface *surface;
    struct wl_listener map;
    struct wl_listener unmap;
    struct wl_listener destroy;
    struct wl_listener request_move;
    struct wl_listener request_resize;
    struct wl_listener set_title;
    int x, y;
    int width, height;
    bool mapped;
    float alpha; /* For animations */
};

/* Ruflo Space (virtual desktop) */
struct ruflo_space {
    struct wl_list link;
    int index;
    char *name;
    struct wl_list windows;
    bool active;
};

/* Function Declarations */
void ruflo_compositor_init(struct ruflo_server *server);
void ruflo_compositor_run(struct ruflo_server *server);
void ruflo_compositor_shutdown(struct ruflo_server *server);

/* Output handling */
void ruflo_output_frame(struct wl_listener *listener, void *data);
void ruflo_output_destroy(struct wl_listener *listener, void *data);

/* View handling */
void ruflo_view_map(struct wl_listener *listener, void *data);
void ruflo_view_unmap(struct wl_listener *listener, void *data);
void ruflo_view_destroy(struct wl_listener *listener, void *data);
void ruflo_view_request_move(struct wl_listener *listener, void *data);
void ruflo_view_request_resize(struct wl_listener *listener, void *data);
void ruflo_view_set_title(struct wl_listener *listener, void *data);

/* macOS-style window management */
void ruflo_open_animation(struct ruflo_view *view);
void ruflo_close_animation(struct ruflo_view *view);
void ruflo_mission_control(struct ruflo_server *server);
void ruflo_switch_space(struct ruflo_server *server, int space_idx);

/* Input event capture for AI */
void ruflo_capture_input_event(struct wlr_input_device *device, void *event);
void ruflo_forward_to_ai_bridge(const char *event_data, size_t len);

/* Screen capture support */
void ruflo_capture_screen(struct wlr_output *output, void *buffer);
struct wl_buffer *ruflo_get_screen_shm(struct ruflo_server *server);

/* AI overlay layer */
void ruflo_create_ai_overlay(struct ruflo_server *server);
void ruflo_destroy_ai_overlay(struct ruflo_server *server);
void ruflo_update_ai_cursor(struct ruflo_server *server, int x, int y);

#endif /* RUFLO_COMPOSITOR_H */
