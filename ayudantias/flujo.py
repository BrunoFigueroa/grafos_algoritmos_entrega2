"""Flujo máximo de costo mínimo (Successive Shortest Paths).

Implementación propia: en cada iteración se busca el camino de costo mínimo
S -> T en la red residual (Dijkstra con potenciales de Johnson) y se aumenta
flujo por él. Al terminar se obtiene el flujo máximo y, entre todos los flujos
máximos, el de menor costo (criterio lexicográfico de la Entrega 1).

Requisito: costos iniciales no negativos (se cumple en nuestro modelo).
"""
import heapq

INF = float("inf")


class RedFlujo:
    def __init__(self):
        self.ids = {}          # nombre de nodo -> índice
        self.nombres = []
        self.ady = []          # ady[u] = lista de índices de aristas
        # aristas en arreglos paralelos; la arista i^1 es la residual de i
        self.dst, self.cap, self.costo = [], [], []

    def nodo(self, nombre):
        if nombre not in self.ids:
            self.ids[nombre] = len(self.nombres)
            self.nombres.append(nombre)
            self.ady.append([])
        return self.ids[nombre]

    def arista(self, u, v, cap, costo=0):
        """Agrega u->v. Devuelve el índice de la arista (para leer su flujo)."""
        if costo < 0:
            raise ValueError("Los costos deben ser no negativos")
        u, v = self.nodo(u), self.nodo(v)
        i = len(self.dst)
        self.dst += [v, u]
        self.cap += [cap, 0]
        self.costo += [costo, -costo]
        self.ady[u].append(i)
        self.ady[v].append(i + 1)
        return i

    def flujo(self, i):
        """Flujo que pasa por la arista i (= capacidad de su residual)."""
        return self.cap[i ^ 1]

    def resolver(self, s, t):
        """Devuelve (flujo_total, costo_total)."""
        s, t = self.ids[s], self.ids[t]
        n = len(self.nombres)
        pot = [0] * n
        flujo_total = costo_total = 0
        while True:
            dist = [INF] * n
            previa = [-1] * n
            dist[s] = 0
            cola = [(0, s)]
            while cola:
                d, u = heapq.heappop(cola)
                if d > dist[u]:
                    continue
                for i in self.ady[u]:
                    if self.cap[i] <= 0:
                        continue
                    v = self.dst[i]
                    nd = d + self.costo[i] + pot[u] - pot[v]
                    if nd < dist[v]:
                        dist[v] = nd
                        previa[v] = i
                        heapq.heappush(cola, (nd, v))
            if dist[t] == INF:
                break
            for v in range(n):
                if dist[v] < INF:
                    pot[v] += dist[v]
            # cuello de botella del camino
            f, v = INF, t
            while v != s:
                i = previa[v]
                f = min(f, self.cap[i])
                v = self.dst[i ^ 1]
            v = t
            while v != s:
                i = previa[v]
                self.cap[i] -= f
                self.cap[i ^ 1] += f
                costo_total += f * self.costo[i]
                v = self.dst[i ^ 1]
            flujo_total += f
        return flujo_total, costo_total
