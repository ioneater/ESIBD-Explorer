call activate base
call conda update -y -n base conda
call conda env update -f esibd.yml --prune