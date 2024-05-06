call activate base
call conda update -y -n base -c conda-forge conda
call conda env update -f esibd.yml --prune