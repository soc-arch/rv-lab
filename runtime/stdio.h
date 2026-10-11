#ifndef CPU_LAB_STDIO_H
#define CPU_LAB_STDIO_H
/* Small buffered console; see README. This is not a complete C library. */
#define EOF (-1)
int printf(const char *format, ...);
int puts(const char *s);
int putchar(int c);
#endif
