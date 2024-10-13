lli modpow(lli x, lli n, lli m) {// (x^n)%m
	if (n == 0) return 1%m;
	lli u = modpow(x,n/2,m);
	u = (u*u)%m;
	if (n%2 == 1) u = (u*x)%m;
	return u;
}

lli binpow(lli a, lli b) {
    if (b == 0) return 1;
    lli res = binpow(a, b / 2);
    if (b % 2) return res * res * a;
    else return res * res;
}
