PREFIX=/usr/local
VERSION=3.1

if [ ! -e ${PREFIX}/oyepa-${VERSION} ] ; then
   mkdir ${PREFIX}/oyepa-${VERSION}
fi

install  * ${PREFIX}/oyepa-${VERSION}
install -d ${PREFIX}/oyepa-${VERSION}/icons
install icons/* ${PREFIX}/oyepa-${VERSION}/icons
ln -fs ${PREFIX}/oyepa-${VERSION}/oyepa.py ${PREFIX}/bin/oyepa
ln -fs ${PREFIX}/oyepa-${VERSION}/oyepa-filemon.py ${PREFIX}/bin/oyepa-filemon
ln -fs ${PREFIX}/oyepa-${VERSION}/mp.py ${PREFIX}/bin/mp.py
ln -fs ${PREFIX}/oyepa-${VERSION}/ds.py ${PREFIX}/bin/ds
ln -fs ${PREFIX}/oyepa-${VERSION}/wnote.py ${PREFIX}/bin/wnote

echo installation complete
