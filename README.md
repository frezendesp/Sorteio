# Sistema de Loterias Automático

Scripts CLI para geração de jogos e análise estatística para Lotofácil, Mega-Sena e Lotomania.

## Arquivos

- `loteria.py`: gera jogos com filtros (`p` paridade, `m` moldura, `r` primos), evita repetições históricas e exporta `txt/json`.
- `stats.py`: sincroniza resultados pela API, gera snapshots de filtros/estatísticas e valida blocos já gerados.

## Exemplos

```bash
python3 loteria.py -lf -f p7 m8 -q 5 -o txt --save
python3 loteria.py -ms -q 30 -o json
python3 stats.py -sync --history 300 -check
python3 stats.py -h 100 -prime-stats -g lotofacil
```

## Dados locais

Os dados são persistidos automaticamente em `data/`:

- `results.json`
- `generated_blocks.json`
- `filters_history.json`


### Estatística de primos por sorteio

Para ver quantos números primos saíram em cada sorteio dos últimos 100 concursos:

```bash
python3 stats.py -h 100 -prime-stats -g lotofacil
```

Campos úteis no JSON:
- `draws[*].prime_count`: quantidade de primos naquele sorteio.
- `distribution`: frequência agregada (ex.: quantos sorteios tiveram 4 primos, 5 primos etc.).
