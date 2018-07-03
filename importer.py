"""import Module for Excel to Salesforce"""
def main():
    """Main entry point"""

    import sys
    from os.path import join

    #
    # Required Parameters
    #

    salesforce_type = str(sys.argv[1])
    client_type = str(sys.argv[2])
    client_subtype = str(sys.argv[3])
    client_emaillist = str(sys.argv[4])

    if len(sys.argv) < 5:
        print ("Calling error - missing required inputs.  Expecting " +
               "salesforce_type client_type client_subtype client_emaillist\n")
        return

    #
    # Optional Parameters
    #

    wait_time = 300
    if '-waittime' in sys.argv:
        wait_time = int(sys.argv[sys.argv.index('-waittime') + 1])

    noupdate = False
    if '-noupdate' in sys.argv:
        noupdate = True

    noexportodbc = False
    if '-noexportodbc' in sys.argv:
        noexportodbc = True

    noexportsf = False
    if '-noexportsf' in sys.argv:
        noexportsf = True

    insert_attempts = 10
    if '-insertattempts' in sys.argv:
        insert_attempts = int(sys.argv[sys.argv.index('-insertattempts') + 1])

    importer_root = ("C:\\repo\\Salesforce-Importer-Private\\Clients\\" + sys.argv[2] +
                     "\\Salesforce-Importer")
    if '-rootdir' in sys.argv:
        importer_root = sys.argv[sys.argv.index('-rootdir') + 1]

    sys.stdout = open(join(importer_root, '..\\importer.log'), 'w')
    print 'Importer Startup'

    importer_directory = join(importer_root, "Clients\\" + client_type)
    print "Setting Importer Directory: " + importer_directory

    # Export External Data
    status_export = ""
    if not noexportodbc:
        print "\n\nExporter - Export External Data\n\n"
        status_export = export_odbc(importer_directory, salesforce_type)

    # Insert Data
    status_import = ""
    if "Invalid Return Code" not in status_export:
        for insert_run in range(0, insert_attempts):

            print "\n\nImporter - Insert Data Process (run: %d)\n\n" % (insert_run)

            status_import = process_data(importer_directory, salesforce_type, client_type,
                                         client_subtype, False, wait_time, client_emaillist, noexportsf)

            # Insert files are empty so continue to update process
            if "import_dataloader (returncode)" not in status_import:
                break

    # Update Data
    if not noupdate and "Unexpected export error" not in status_import:
        print "\n\nImporter - Update Data Process\n\n"
        process_data(importer_directory, salesforce_type, client_type,
                     client_subtype, True, wait_time, client_emaillist, noexportsf)

    print "\nImporter process completed\n"

def process_data(importer_directory, salesforce_type, client_type,
                 client_subtype, update_mode, wait_time, client_emaillist, noexportsf):
    """Process Data based on data_mode"""

    from os import makedirs
    from os.path import exists

    data_mode = "Insert"
    if update_mode:
        data_mode = "Update"

    subject = "Process Data (" + data_mode + ") Results -"
    file_path = importer_directory + "\\Status"
    if not exists(file_path):
        makedirs(file_path)

    body = "Process Data (" + data_mode + ")\n\n"

    # Export data from Salesforce
    status_export = ""
    try:
        if not noexportsf and "Error" not in subject:
            status_export = export_dataloader(importer_directory, salesforce_type)
        else:
            status_export = "Skipping export from Salesforce"
    except Exception as ex:
        subject += " Error Export"
        body += "\n\nUnexpected export error:" + str(ex)
    else:
        body += "\n\nExport\n" + status_export

    # Export data from Excel
    try:
        if "Error" not in subject:
            status_export = refresh_and_export(importer_directory, salesforce_type, client_type,
                                               client_subtype, update_mode, wait_time)
        else:
            status_export = "Skipping export from Excel"
    except Exception as ex:
        subject += " Error Export"
        body += "\n\nUnexpected export error:" + str(ex)
    else:
        body += "\n\nExport\n" + status_export

    # Import data into Salesforce
    status_import = ""

    try:
        if "Error" not in subject:
            status_import = import_dataloader(importer_directory,
                                              client_type, salesforce_type, data_mode)
        else:
            status_import = "Error detected so skipped"
    except Exception as ex:
        subject += " Error Import"
        body += "\n\nUnexpected import error:" + str(ex)
    else:
        body += "\n\nImport\n" + status_import

    if "Error" not in subject:
        subject += " Successful"

    # Send email results
    send_email(client_emaillist, subject, body, file_path)

    return status_import

def refresh_and_export(importer_directory, salesforce_type,
                       client_type, client_subtype, update_mode, wait_time):
    """Refresh Excel connections"""

    #import datetime
    import os
    import os.path
    import time
    import win32com.client as win32

    try:
        refresh_status = "refresh_and_export\n"
        excel_connection = win32.gencache.EnsureDispatch("Excel.Application")
        excel_file_path = importer_directory + "\\"
        workbooks = excel_connection.Workbooks
        workbook = workbooks.Open((
            excel_file_path + client_type + "-" + client_subtype + "_" + salesforce_type + ".xlsx"))

        # Uncomment if you want to see the Excel file opened
        #excel_connection.Visible = True

        # Comment if you want to see alerts
        excel_connection.DisplayAlerts = False

        #for connection in workbook.Connections:
            #print connection.name
            # BackgroundQuery does not work so have to do manually in Excel for each Connection
            #connection.BackgroundQuery = False

        # RefreshAll is Synchronous iif
        #   1) Enable background refresh disabled/unchecked in xlsx for all Connections
        #   2) Include in Refresh All enabled/checked in xlsx for all Connections
        #   To verify: Open xlsx Data > Connections > Properties for each to verify
        message = "\nRefreshing all connections..."
        print message
        refresh_status += message + "\n"

        workbook.RefreshAll()

        # Wait for excel to finish refresh
        message = ("Pausing " + str(wait_time) +
                   " seconds to give Excel time to complete data queries...")
        print message
        refresh_status += message + "\n"
        time.sleep(wait_time)

        message = "Refreshing all connections...Completed"
        print message
        refresh_status += message + "\n"

        if not os.path.exists(excel_file_path + "Import\\"):
            os.makedirs(excel_file_path + "Import\\")

        #date_tag = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        for sheet in workbook.Sheets:
            # Only export update, insert, or report sheets
            sheet_name_lower = sheet.Name.lower()
            if ("update" not in sheet_name_lower
                    and "insert" not in sheet_name_lower
                    and "report" not in sheet_name_lower):
                continue

            message = "Exporting csv for sheet: " + sheet.Name
            print message
            refresh_status += message + "\n"

            excel_connection.Sheets(sheet.Name).Select()
            sheet_file = excel_file_path + "Import\\" + sheet.Name + ".csv"

            # Save report to Status to get attached to email
            if "report" in sheet.Name.lower():
                sheet_file = excel_file_path + "Status\\" + sheet.Name + ".csv"

            # Check for existing file
            if os.path.isfile(sheet_file):
                os.remove(sheet_file)

            workbook.SaveAs(sheet_file, 6)

            # Update check to make sure insert sheet is empty
            if update_mode and "insert" in sheet.Name.lower() and contains_data(sheet_file):
                raise Exception("Update Error", (
                    "Insert sheet contains data and should be empty during update process: " +
                    sheet_file))

    except Exception as ex:
        refresh_status += "Unexpected error:" + str(ex)
        raise Exception("Export Error", refresh_status)

    finally:
        workbook.Close(False)
        # Marshal.ReleaseComObject(workbooks)
        # Marshal.ReleaseComObject(workbook)
        # Marshal.ReleaseComObject(excel_connection)
        excel_connection.Quit()

    return refresh_status

def contains_data(file_name):
    """Check if file contains data after header"""

    line_index = 1
    with open(file_name) as file_open:
        for line in file_open:
            # Check if line empty
            line_check = line.replace(",", "")
            line_check = line_check.replace('"', '')
            if (line_index == 2 and line_check != "\n"):
                return True
            elif line_index > 2:
                return True

            line_index += 1

    return False

def import_dataloader(importer_directory, client_type, salesforce_type, data_mode):
    """Import into Salesforce using DataLoader"""

    import os
    from os import listdir
    from os.path import join
    from subprocess import Popen, PIPE

    bat_path = importer_directory + "\\DataLoader"
    import_path = importer_directory + "\\Import"

    return_code = ""
    return_stdout = ""
    return_stderr = ""

    for file_name in listdir(bat_path):
        if not data_mode in file_name or ".sdl" not in file_name:
            continue

        # Check if associated csv has any data
        sheet_name = os.path.splitext(file_name)[0]
        import_file = join(import_path, sheet_name + ".csv")
        if not os.path.exists(import_file) or not contains_data(import_file):
            continue

        bat_file = (join(bat_path, "RunDataLoader.bat")
                    + " " + salesforce_type + " "  + client_type + " " + sheet_name)

        message = "Starting Import Process: " + bat_file + " for file: " + import_file
        print message
        return_stdout += message + "\n"
        import_process = Popen(bat_file, stdout=PIPE, stderr=PIPE)

        stdout, stderr = import_process.communicate()

        return_code += "import_dataloader (returncode): " + str(import_process.returncode)
        return_stdout += "\n\nimport_dataloader (stdout):\n" + stdout
        return_stderr += "\n\nimport_dataloader (stderr):\n" + stderr

        if (import_process.returncode != 0
                or "Error" in return_stdout
                or "We couldn't find the Java Runtime Environment (JRE)" in return_stdout):
            raise Exception("Invalid Return Code", return_code + return_stdout + return_stderr)

        status_path = importer_directory + "\\status"

        for file_name_status in listdir(status_path):
            file_name_status_full = join(status_path, file_name_status)
            if "error" in file_name_status_full and contains_data(file_name_status_full):
                raise Exception("error file contains data: " + file_name_status_full, (
                    return_code + return_stdout + return_stderr))

        message = "Finished Import Process: " + bat_file + " for file: " + import_file
        print message

    return return_code + return_stdout + return_stderr

def export_dataloader(importer_directory, salesforce_type):
    """Export out of Salesforce using DataLoader"""

    from os.path import exists
    from subprocess import Popen, PIPE

    exporter_directory = importer_directory.replace("Importer", "Exporter")
    if "\\Salesforce-Exporter\\" in exporter_directory:
        exporter_directory += "\\..\\..\\.."

    bat_file = exporter_directory + "\\exporter.bat " + salesforce_type

    return_code = ""
    return_stdout = ""
    return_stderr = ""

    if not exists(exporter_directory):
        print "Skip Export Process (export not detected)"
    else:
        message = "Starting Export Process: " + bat_file
        print message
        return_stdout += message + "\n"
        export_process = Popen(bat_file, stdout=PIPE, stderr=PIPE)

        stdout, stderr = export_process.communicate()

        return_code += "\n\nexport_dataloader (returncode): " + str(export_process.returncode)
        return_stdout += "\n\nexport_dataloader (stdout):\n" + stdout
        return_stderr += "\n\nexport_dataloader (stderr):\n" + stderr

        if (export_process.returncode != 0
                or "Error" in return_stdout
                or "We couldn't find the Java Runtime Environment (JRE)" in return_stdout):
            raise Exception("Invalid Return Code", return_code + return_stdout + return_stderr)

    return return_code + return_stdout + return_stderr

def export_odbc(importer_directory, salesforce_type):
    """Export out of Salesforce using DataLoader"""

    from os.path import exists
    from subprocess import Popen, PIPE

    exporter_directory = importer_directory.replace("Salesforce-Importer", "ODBC-Exporter")
    if "\\ODBC-Exporter\\" in exporter_directory:
        exporter_directory += "\\..\\..\\.."

    bat_file = exporter_directory + "\\exporter.bat " + salesforce_type

    return_code = ""
    return_stdout = ""
    return_stderr = ""

    if not exists(exporter_directory):
        print "Skip ODBC Export Process (export not detected)"
    else:
        message = "Starting ODBC Export Process: " + bat_file
        print message
        return_stdout += message + "\n"
        export_process = Popen(bat_file, stdout=PIPE, stderr=PIPE)

        stdout, stderr = export_process.communicate()

        return_code += "\n\nexport_odbc (returncode): " + str(export_process.returncode)
        return_stdout += "\n\nexport_odbc (stdout):\n" + stdout
        return_stderr += "\n\nexport_odbc (stderr):\n" + stderr

        if (export_process.returncode != 0
                or "Error" in return_stdout
                or "We couldn't find the Java Runtime Environment (JRE)" in return_stdout):
            raise Exception("Invalid Return Code", return_code + return_stdout + return_stderr)

    return return_code + return_stdout + return_stderr

def send_email(client_emaillist, subject, text, file_path):
    """Send email via O365"""

    message = "\n\nPreparing email results\n"
    print message

    send_to = client_emaillist.split(";")
    send_from = 'db.powerbi@501commons.org'
    server = "smtp.office365.com"

    #https://stackoverflow.com/questions/3362600/how-to-send-email-attachments
    import base64
    import os
    import smtplib
    from os.path import basename
    from email.mime.application import MIMEApplication
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.utils import COMMASPACE, formatdate

    msg = MIMEMultipart()

    msg['From'] = send_from
    msg['To'] = COMMASPACE.join(send_to)
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = subject

    msg.attach(MIMEText(text))

    from os import listdir
    from os.path import isfile, join, exists
    onlyfiles = [join(file_path, f) for f in listdir(file_path)
                 if isfile(join(file_path, f))]

    for file_name in onlyfiles:
        if contains_data(file_name) and ".sent" not in file_name:

            message = "Email attaching file: " + file_name + "\n"
            print message

            with open(file_name, "rb") as file_name_open:
                part = MIMEApplication(
                    file_name_open.read(),
                    Name=basename(file_name)
                    )

            # After the file is closed
            part['Content-Disposition'] = 'attachment; filename="%s"' % basename(file_name)
            msg.attach(part)

            # Rename file so do not attached again
            sent_file = file_path + '.sent'
            if exists(sent_file):
                os.remove(sent_file)

            os.rename(file_name, sent_file)

    server = smtplib.SMTP(server, 587)
    server.starttls()
    server_password = os.environ['SERVER_EMAIL_PASSWORD']
    server.login(send_from, base64.b64decode(server_password))
    text = msg.as_string()
    server.sendmail(send_from, send_to, text)
    server.quit()

    message = "\nSent email results\n"
    print message

def send_salesforce():
    """Send results to Salesforce to handle notifications"""
    #Future update to send to salesforce to handle notifications instead of send_email
    #https://developer.salesforce.com/blogs/developer-relations/2014/01/
    #python-and-the-force-com-rest-api-simple-simple-salesforce-example.html

if __name__ == "__main__":
    main()