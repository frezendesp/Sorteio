# Sistema de Loterias Automático

## lotofacil.py

Fluxo recomendado:

1. Gerar bloco em buffer
```bash
python3 lotofacil.py -f p5 m9 s190-220 -q 24 --fechamento 14 --optimize --buffer
```
2. Visualizar bloco em matriz ANSI 5x5
```bash
python3 lotofacil.py --view --view-source buffer
# ou por ID
python3 lotofacil.py --view --view-id 3 --view-source buffer
```
3. Commit do buffer para histórico de jogados
```bash
python3 lotofacil.py --commit 3
```
4. Auditoria do último bloco jogado contra API oficial
```bash
python3 lotofacil.py --check-last
```

### Filtros suportados
- `mN` Moldura
- `cN` Centro
- `+N` Cruz
- `xN` X
- `pN` Primos
- `fN` Fibonacci
- `sMIN-MAX` ou `sN` Soma
- `vN` Vazios consecutivos máximos por linha/coluna
- `eN` Pares (extra)

## stats.py

Exemplos:

```bash
python3 stats.py -sync -h 300
python3 stats.py -h 100 -prime-stats -g lotofacil
python3 stats.py --create-group Preset_A p5 m9 s190-220
python3 stats.py --ciclo
python3 stats.py --affinity 3 -g lotofacil -h 200
python3 stats.py --coverage 3
python3 stats.py --backtest 3 -h 120
```

Saídas são em JSON para facilitar automação.
