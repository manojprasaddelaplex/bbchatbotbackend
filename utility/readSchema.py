def readHcpPatientsSchema():
    with open('data\\HcpPatients.txt', 'r') as file:
        content = file.read()
    return content

def readPoliceForceSchema():
    with open('data\\PoliceForce.txt', 'r') as file:
        content = file.read()
    return content
