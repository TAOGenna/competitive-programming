typedef long long C;
typedef complex<C> P;
#define X real()
#define Y imag()

bool myWay(complex<C> a, complex<C> b){
    if (real(a) == real(b))
        return imag(a) < imag(b);
    return real(a) < real(b);
}

C det(P a, P b){return (conj(a)*b).Y;}

C pointLoc(P s1,P s2,P p){return det(p-s1,p-s2);}

vector<P> convexHull(vector<P> points) {// it will return a vector with the points containing the convex hull
  sort(points.begin(), points.end(),myWay);
  vector<P> hull;
  for (int phase = 0; phase < 2; ++phase) {
    auto start = hull.size();
    for (auto& point : points) {
      while (hull.size() >= start+2 && pointLoc(hull[hull.size()-2],hull.back(),point)<=0)
        hull.pop_back();
      hull.push_back(point);
    }
    hull.pop_back();
    reverse(points.begin(),points.end());
  }
  if (hull.size() == 2 && hull[0] == hull[1]) hull.pop_back();
  return hull;
}

