vector<lli> factors(lli n) {
  vector<lli> f;
  for (lli x = 2; x*x <= n; x++) {
    while (n%x == 0) {
      f.push_back(x);
      n /= x;
    }
  }
  if (n > 1) f.push_back(n);
  return f;
}
