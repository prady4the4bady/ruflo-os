# Meson build file for Ruflo Compositor
project('ruflo-compositor', 'c', version: '1.0.0', default_options: ['warning_level=2'])

# Dependencies
wayland_server = dependency('wayland-server')
libweston = dependency('libweston-12')
pixman = dependency('pixman-1')
egl = dependency('egl')
gles2 = dependency('gles2')
libinput = dependency('libinput')
xkbcommon = dependency('xkbcommon')
wayland_protocols = dependency('wayland-protocols')

# Sources
sources = files(
    'ruflo-compositor.c',
)

# Protocol files (generate from XML)
wayland_scanner = find_program('wayland-scanner')
custom_target('xdg-shell-protocol',
    input: 'xdg-shell.xml',
    output: ['xdg-shell-protocol.c', 'xdg-shell-client-protocol.h'],
    command: [wayland_scanner, 'private-code', '@INPUT@', '@OUTPUT0@'],
)

# Executable
executable('ruflo-compositor',
    sources,
    dependencies: [
        wayland_server,
        libweston,
        pixman,
        egl,
        gles2,
        libinput,
        xkbcommon,
        wayland_protocols,
    ],
    c_args: ['-D_GNU_SOURCE'],
    install: true,
    install_dir: get_option('prefix') / 'bin',
)

# Install header
install_headers('ruflo-compositor.h', subdir: 'ruflo')
