# 🎯 Morale / Pressure System (Assault)

## ✅ Concepto

La moral (pressure) NO se incrementa directamente.

Se calcula a partir de:
- pérdidas acumuladas (`losses`)
- umbral fijo = **12 puntos**

---

## 🧠 Variables por jugador

```python
losses   # acumulador de daño
pressure # estado de moral
```

---

## 💣 Regla principal

Cada vez que:

```text
losses >= 12
```

Entonces:

```python
pressure += 1
losses -= 12
```

(Repetir mientras se cumpla la condición)

---

## 🔁 Función base

```python
def add_losses(side, value):
    side.losses += value

    while side.losses >= 12:
        side.losses -= 12
        side.pressure += 1
```

---

## ⚔️ Cuándo llamar a `add_losses`

### ✅ En combate

- unidad destruida → sumar valor completo
- unidad dañada → sumar mitad del valor

---

## 🎯 Objetivos (ajuste directo)

```python
# capturar objetivo
pressure -= VP

# perder objetivo
pressure += VP
```

---

## 🟣 Eventos especiales

Reglas de escenario pueden hacer:

```python
pressure += X
pressure -= X
```

---

## 🔚 Check de estado (final de turno)

Evaluar al final de la fase de organización:

```python
if pressure >= surrender:
    end_game()

elif pressure >= rout:
    check_rout()

elif pressure >= retreat:
    check_retreat()
```

---

## 🧩 Ejemplo

```python
losses = 10

add_losses(5)

# resultado:
# losses = 3
# pressure +1
```

---

## 🧠 Resumen

```
daño → losses
cada 12 → +1 pressure
pressure → dispara estados (retirada, rotta, resa)
```
