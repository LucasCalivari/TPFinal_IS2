#*------------------------------------------------------------------------
#* Ingeniería de Software II
#* Patrones de Creación
#* Proxy
#* UADER - Ingeniería de Software II
#* Dr. Pedro E. Colla
#*------------------------------------------------------------------------

class College:
    '''Recurso que se quiere restringir el acceso'''

    def studyingInCollege(self):
        print("ID del estudiante es correcto")


class CollegeProxy:
    '''Solo accede al recurso de uso intensivo si se dan condiciones previas'''

    def __init__(self):

        self.feeBalance = 1000
        self.id = None
        self.college = None

    def studyingInCollege(self):

        print("\n\nAcceso al Proxy. Revisa el saldo antes de acceder al recurso")
        if self.feeBalance <= 500:
            self.college = College()
            print("Validación de ID(%s) contra el database externo:\n" % (self.id))
            self.college.studyingInCollege()
        else:
            print("Estudiante ID(%s) Debe ponerse al día con la matricula" % (self.id))

"""main method"""

if __name__ == "__main__":

    import os
    os.system('clear')

#*--- Instancia los objetos a operar back to back
    
    collegeProxy = CollegeProxy()


    # Estudiante con pagos demorados
    collegeProxy.id="Gomez,Pepe"
    collegeProxy.studyingInCollege()
    
    # Estudiante con pagos al dia
    collegeProxy.id="Alvarez,Mica"
    collegeProxy.feeBalance = 100
    collegeProxy.studyingInCollege()

