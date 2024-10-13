lli F[MAXN], INV[MAXN], FI[MAXN];
// ...
F[0] = 1; rep(i, 1, MAXN) F[i] = F[i-1]*i %M;
INV[1] = 1; rep(i, 2, MAXN) INV[a] = M - (ll)(M/a)*INV[M%a]%M;
FI[0] = 1; rep(i, 1, MAXN) FI[i] = FI[i-1]*INV[i] %M;
