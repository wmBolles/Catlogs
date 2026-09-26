#include <stdio.h>
#include <stdlib.h>
#include <string.h>

const char *sec_key = "CatLogsSecKey123";
int sec_key_len = 16;
int global_offset = 0;

int main() {
    const char *buf = "[2026-09-19T20:12:38] --- CatLogs";
    int len = strlen(buf);
    char *enc = malloc(len + 1);
    for (int i = 0; i < len; i++) {
        enc[i] = buf[i] ^ sec_key[(global_offset + i) % sec_key_len];
    }
    enc[len] = '\0';
    
    printf("Original: %s\n", buf);
    printf("Encrypted: ");
    for(int i=0; i<len; i++) printf("%02x ", (unsigned char)enc[i]);
    printf("\n");
    return 0;
}
