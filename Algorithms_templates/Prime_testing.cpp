bool prime(lli n) {
  if (n < 2) return false;
  for (lli x = 2; x*x <= n; x++) {
    if (n%x == 0) return false;
  }
  return true;
}
