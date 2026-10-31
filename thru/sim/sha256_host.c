/* Portable FIPS 180-4 SHA-256 implementing the SDK's tsdk_sha256_* API, for HOST builds only.
 * The SDK's own tn_sdk_sha256.c uses RISC-V Zknh instructions and cannot run on the host.
 * Checked against Python hashlib in thru/tests (test_sha256_matches_hashlib). */
#include <string.h>
#include <thru-sdk/c/tn_sdk_sha256.h>

static uint const K[64] = {
  0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,0x3956c25bu,0x59f111f1u,0x923f82a4u,0xab1c5ed5u,
  0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,
  0xe49b69c1u,0xefbe4786u,0x0fc19dc6u,0x240ca1ccu,0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,
  0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,0xc6e00bf3u,0xd5a79147u,0x06ca6351u,0x14292967u,
  0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,0x650a7354u,0x766a0abbu,0x81c2c92eu,0x92722c85u,
  0xa2bfe8a1u,0xa81a664bu,0xc24b8b70u,0xc76c51a3u,0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,
  0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,0x391c0cb3u,0x4ed8aa4au,0x5b9cca4fu,0x682e6ff3u,
  0x748f82eeu,0x78a5636fu,0x84c87814u,0x8cc70208u,0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u };

#define ROR(x, n) (((x) >> (n)) | ((x) << (32 - (n))))

static void block(uint s[8], uchar const *p) {
  uint w[64];
  for (int i = 0; i < 16; i++) w[i] = (uint)p[4*i] << 24 | (uint)p[4*i+1] << 16 | (uint)p[4*i+2] << 8 | (uint)p[4*i+3];
  for (int i = 16; i < 64; i++) {
    uint s0 = ROR(w[i-15], 7) ^ ROR(w[i-15], 18) ^ (w[i-15] >> 3);
    uint s1 = ROR(w[i-2], 17) ^ ROR(w[i-2], 19) ^ (w[i-2] >> 10);
    w[i] = w[i-16] + s0 + w[i-7] + s1;
  }
  uint a = s[0], b = s[1], c = s[2], d = s[3], e = s[4], f = s[5], g = s[6], h = s[7];
  for (int i = 0; i < 64; i++) {
    uint t1 = h + (ROR(e, 6) ^ ROR(e, 11) ^ ROR(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + w[i];
    uint t2 = (ROR(a, 2) ^ ROR(a, 13) ^ ROR(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
    h = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
  }
  s[0] += a; s[1] += b; s[2] += c; s[3] += d; s[4] += e; s[5] += f; s[6] += g; s[7] += h;
}

tsdk_sha256_t * tsdk_sha256_init(tsdk_sha256_t *sha) {
  static uint const H0[8] = { 0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u };
  memcpy(sha->state, H0, sizeof H0); sha->buf_used = 0; sha->bit_cnt = 0;
  return sha;
}

tsdk_sha256_t * tsdk_sha256_append(tsdk_sha256_t *sha, void const *data, ulong sz) {
  uchar const *p = (uchar const *)data;
  sha->bit_cnt += sz * 8UL;
  while (sz) {
    ulong n = TSDK_SHA256_BLOCK_SZ - sha->buf_used; if (n > sz) n = sz;
    memcpy(sha->buf + sha->buf_used, p, n); sha->buf_used += n; p += n; sz -= n;
    if (sha->buf_used == TSDK_SHA256_BLOCK_SZ) { block(sha->state, sha->buf); sha->buf_used = 0; }
  }
  return sha;
}

void * tsdk_sha256_fini(tsdk_sha256_t *sha, void *hash) {
  ulong bits = sha->bit_cnt;
  uchar pad = 0x80; ulong zero = 0;
  tsdk_sha256_append(sha, &pad, 1);
  while (sha->buf_used != 56) tsdk_sha256_append(sha, &zero, 1);
  uchar len[8]; for (int i = 0; i < 8; i++) len[i] = (uchar)(bits >> (56 - 8 * i));
  tsdk_sha256_append(sha, len, 8);
  uchar *o = (uchar *)hash;
  for (int i = 0; i < 8; i++) { o[4*i] = (uchar)(sha->state[i] >> 24); o[4*i+1] = (uchar)(sha->state[i] >> 16); o[4*i+2] = (uchar)(sha->state[i] >> 8); o[4*i+3] = (uchar)sha->state[i]; }
  return hash;
}

void * tsdk_sha256_hash(void const *data, ulong sz, void *hash) {
  tsdk_sha256_t s; tsdk_sha256_init(&s); tsdk_sha256_append(&s, data, sz); return tsdk_sha256_fini(&s, hash);
}

/* exported for the hashlib cross-check */
void sim_sha256(void const *data, ulong sz, uchar out[32]) { tsdk_sha256_hash(data, sz, out); }
