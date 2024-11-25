const int N=1005;
int tree[2*N];
int n;
void add(int k, int x) {//add(position,value)
	k += n-1;
	tree[k] += x;
	for (k /= 2; k >= 1; k /= 2) {
		tree[k] = tree[2*k]+tree[2*k+1];
	}
}

int sum(int a, int b) { //query[a,b]
	a += n-1; b += n-1;
	int s = 0;
	while (a <= b) {
		if (a%2 == 1) s += tree[a++];
		if (b%2 == 0) s += tree[b--];
		a /= 2; b /= 2;
	}
	return s;
}

