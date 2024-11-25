typedef long double C
typedef long double C;
typedef complex<C> P;
#define X real()
#define Y imag()


 Create a point -> P my_poiny={cx,cy}
 FUNCTIONS : should only be used when the coordinate type is LONG DOUBLE(OR ANOTHER FLOATING POINT)
 1) lenght of a vector v={x,y} -> abs(v)
 2) Distance between two points v and u -> abs(v-u)
 3) Angle of a vector v with respect to the x-axis 
		 -> arg(v) (in radians, r radians is (r)(180/pi))
 4) Function polar build a vector of lenght s and angle a(in radians)
		 -> polar(s,a) {extra: rotates vectors by angle B is multiple polar(1,B)*my_vector}
 5) Determinant or cross product of vectors a and b  
		-> C det(P a, P b){return (conj(a)*b).Y;}
		  axb>0 is turn to the left , axb==0 is go straight, axb<0 is turn to the right
 		5.1) Testing Point Location 
			 asuming a line s1---s2 and a point p // we want to know the location of p //
			C pointLoc(P s1,P s2,P p){return det(p-s1,p-s2;)}  // if >0 ->right, if <0 -> left, if ==0 -> through the line
 		5.2) type Line Segment Intersection(P p1,P p2,P s1, P s2){
				Case 1 : everyone on the same line
				if(pointLoc(p1,p2,s1)==0 and pointLoc(p1,p2,s2)==0)
				Case 2 : the line segmenents have a common vertex, the only intersection
				if(a==c or b==c or b==d or a==d)
				Case 3 : there's only one intersection point that is not a vertex of any line
				if(pointLoc(s1,s2,p1)!=pointLoc(s1,s2,p2) and pointLoc(p1,p2,s1)!=pointLoc(p1,p2,s2))
		}			
6) Distance from a Point to a Line// think about the triangle area				
			Area_triangle=|(a-c)x(b-c)|/2 , a,b,c are the vertices of the triangle 
			Area_triangle=(|s2-s1|*d)/2 
			then -> C dist(P s1,P s2,P p){return det(s1-p,s2-p)/abs(s1-s2);}
7) Point in a Polygon O(#lines): send a ray from the point to an arbitrary direction
						 and calculate the number of touches in the boundary of the polygon
						if(touches%2==1) is inside of the polygon
						else is outside of the polygon 
8) Polygon Area: the idea is a sum of trapezoids where if(X_i+1>X_i) area is positive;else is negative
			Area= (1/2)*abs(for(int i=1;i<=n-1;i++) det(Point[i],Point[i+1]) ) , where Point[1]=Point[n]
9) Pick's Theorem: Area=a+b/2-1 where a=#integers points inside the polygon and b=#integers points on the boundary
10) 

