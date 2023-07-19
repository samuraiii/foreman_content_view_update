#!/usr/bin/python3
# vim: set fileencoding=utf-8 :
# Managed by puppet
from datetime import datetime
from re import match
from sys import argv, exit, stdout  # pylint: disable=redefined-builtin
from time import sleep
from typing import Union
from requests import Session
from urllib3 import disable_warnings, exceptions

USER: str = 'api'
API_TOKEN: str = '<FOREMAN_API_KEY>'
URL_BASE: str = 'https://<FOREMAN_API_HOST>'
SESSION: Session = Session()
SESSION.auth = (USER, API_TOKEN)
SESSION.headers.update({'Content-Type': 'application/json'})
SESSION.verify = False

disable_warnings(exceptions.InsecureRequestWarning)


def make_request(
    request: str,
    parametres: Union[dict, None] = None,
    request_type: str = 'get'
    ) -> dict:
    '''
    Does actual API call
    '''
    request_response: dict
    if parametres is None:
        parametres: dict = {}
    if request_type == 'get':
        if 'per_page' in parametres:
            if parametres['per_page'] is False:
                del parametres['per_page']
        else:
            parametres['per_page'] =  '999_999_999'
        request_response =  SESSION.get(URL_BASE + request, allow_redirects=True, \
            params=parametres).json()

    elif request_type == 'post':
        request_response =  SESSION.post(URL_BASE + request, allow_redirects=True, \
            json=parametres).json()

    elif request_type == 'delete':
        request_response =  SESSION.delete(URL_BASE + request, allow_redirects=True).json()

    else:
        log('Undefined type in get_request()!')
        exit(2)
    return request_response


def noop(*args) -> None:  # pylint: disable=unused-argument
    '''
    /dev/null function
    '''


def date() -> str:
    '''
    Get current time and date
    '''
    return datetime.isoformat(datetime.now(),timespec='seconds')


def stdout_write(stdout_message: str) -> None:
    '''
    Write non-persistent messages
    '''
    stdout.write(stdout_message + '\r')
    stdout.flush()


def log(message: str, method: str = 'print', newline: bool = False) -> None:
    '''
    Write to terminal with current time nad date
    '''
    newline_char: str = ''
    if newline:
        newline_char = '\n'
    output_message: str  = f'{newline_char}{date()}: {message}'
    if method == 'print':
        print(output_message)
    else:
        stdout_write(output_message.ljust(100))


def usage(ecode) -> None:
    '''
    Prints help with optional error
    '''
    print('Usage:')
    print(f'"# {argv[0]} -c"\n or\n"# {argv[0]} --cleanup"')
    print('\tUpdates all composite views and removes all obsolete versions of both composite')
    print('\tand noncomposite views.\n')
    print(f'"# {argv[0]} -h"\n or\n"# {argv[0]} --help"')
    print('\tDisplays this help text\n')
    print(f'"# {argv[0]}')
    print('\tDoes update af all noncomposite views, and than same as with "-c" or "--cleanup"')
    if int(ecode) > 0:
        cli_arguments: str = ' '.join(argv)
        print(f'\n\nInvalid argument(s) detected "# {cli_arguments}" !!!\n')
    exit(ecode)


def check_continue() -> bool:
    '''
    Checks if ther are any runnig or paused tasks before continuing
    '''
    error_count: int = 0
    continue_ok: bool = False
    sleep(5)
    while True:
        sleep_time: int = 10
        paused_tasks: dict = make_request('/foreman_tasks/api/tasks/', \
            parametres={'search': 'state = paused'})
        running_tasks: dict = make_request('/foreman_tasks/api/tasks/', \
            parametres={'search': 'state = running'})
        if 'subtotal' in running_tasks and 'subtotal' in paused_tasks:
            if (running_tasks['subtotal'] + paused_tasks['subtotal']) == 0:
                stdout_write(' '.rjust(100))
                continue_ok = True
            else:
                log(f"Waiting for {running_tasks['subtotal']} running and "\
                    f"{paused_tasks['subtotal']} paused tasks to finish...", method='stdout')
                if paused_tasks['subtotal'] > 0:
                    log(f"Unpausing {paused_tasks['subtotal']} tasks.", newline=True)
                    noop(make_request('/foreman_tasks/api/tasks/bulk_resume', request_type='post'))
        else:
            sleep_time = 5
            error_count += 1
        if error_count > 4:
            log('CRITICAL: Could not get response from server exiting.')
            exit(1)
        if not continue_ok:
            sleep(sleep_time)
        else:
            return continue_ok


def progressbar(progress_number: float, multiplicator: Union[None, float] = None) -> str:
    '''
    Creates progressbar
    '''
    barsize: int = 70
    progress_number_w: float
    cursor: str
    if multiplicator is not None:
        progress_number_w = progress_number * multiplicator
    elif progress_number > 1:
        progress_number_w = progress_number
    else:
        progress_number_w = progress_number * 100
    if progress_number_w == 100:
        cursor = ''
    else:
        cursor = '>'
    bar_length: int = int(barsize*(progress_number_w/100))
    bar_content: str = (''.rjust(bar_length, '=')+cursor).ljust(barsize)
    percent: str = str(int(progress_number_w)).rjust(3)
    return f' [{bar_content}] {percent}% '


def show_task_progress(task_id: str, action: str = 'update') -> None:
    '''
    Prints task progress
    '''
    task_unpaused: int = 0
    done: bool = False
    while True:
        task_state: dict = make_request(f'/foreman_tasks/api/tasks/{task_id}/details')
        log(progressbar(task_state['progress']),method='stdout')
        if task_state['state'] == 'paused':
            if task_unpaused > 2:
                log(f"Task {action} '{task_state['input']['content_view']['name']}' "\
                    "failed three times.", newline=True)
                log(f'Please review at {URL_BASE}/foreman_tasks/tasks/{task_id}')
                exit(3)
            noop(make_request('/foreman_tasks/api/tasks/bulk_resume', \
                parametres={'task_ids': [task_id]}))
            task_unpaused += 1
        elif task_state['state'] == 'stopped':
            log(f"Task {action} '{task_state['input']['content_view']['name']}' finished.", \
                newline=True)
            done = True
        if not done:
            sleep(3)
        else:
            return



def delete_content_view_versions(content_view_id: str, content_view_name: str) -> None:
    '''
    Deletes obsolete content view versions
    '''
    content_view_versions: dict = make_request(
        f'/katello/api/content_views/{content_view_id}/content_view_versions')
    delete_content_view_version: bool = False
    versions_to_keep: int = 3
    log(f"Deleting {len(content_view_versions['results']) - versions_to_keep} "\
        f"obsolete versions of content view '{content_view_name}'.")
    for content_view_version in content_view_versions['results']:
        if delete_content_view_version:
            if len(content_view_version['environments']) == 0:
                check_continue()
                noop(make_request(
                    f"/katello/api/content_view_versions/{content_view_version['id']}", \
                        request_type='delete'))
            else:
                log(f"Cannot delete the content view version '{content_view_name}' " \
                    f"'{content_view_version['version']}' (id:{content_view_version['id']})! " \
                    "Because it is part of the lifecycle environment.")
        else:
            # skip latest versions_to_keep versions
            if versions_to_keep < 2:
                delete_content_view_version = True
            else:
                versions_to_keep = versions_to_keep - 1



if __name__ == '__main__':
    CLEANUP: bool = False
    for argument in argv:
        if argument == argv[0]:
            pass
        elif match(r'^--?h(elp)?$', argument):
            usage(0)
        elif match(r'^--?c(leanup)?$', argument):
            CLEANUP = True
        else:
            usage(10)

    # list of noncomposites is needed for a final cleanup
    noncomposite_views: dict = make_request('/katello/api/content_views', \
        parametres={'noncomposite': 'true', 'order': 'name ASC'})
    # update non composite views
    if not CLEANUP:
        log('Starting non-composite content views updates.')
        for noncomposite_view in noncomposite_views['results']:
            if noncomposite_view['label'] != 'Default_Organization_View':
                check_continue()
                log(f"Updating content view '{noncomposite_view['name']}' "\
                    f"(id:{noncomposite_view['id']})")
                nc_update_response: dict = make_request(
                    f"/katello/api/content_views/{noncomposite_view['id']}/publish", \
                        request_type='post')
                if 'id' in nc_update_response:
                    show_task_progress(nc_update_response['id'])
                else:
                    log("Failed to update non-composite content view " \
                        f"'{noncomposite_view['name']}' (id:{noncomposite_view['id']})!")
        log('All noncomposite views updated.')

    # publish, promote and clean composite views
    log('Starting composite content views updates.')
    composite_views: dict = make_request('/katello/api/content_views', \
        parametres={'composite': 'true', 'order': 'name ASC'})
    for composite_view in composite_views['results']:
        environments: set = set()
        for environment in composite_view['environments']:
            if environment['label'] != 'Library':
                environments.add(environment['id'])
        check_continue()
        log(f"Updating content view '{composite_view['name']}' (id:{composite_view['id']})")
        c_update_response: dict = make_request(
            f"/katello/api/content_views/{composite_view['id']}/publish", \
                request_type='post')
        if 'id' in c_update_response:
            show_task_progress(c_update_response['id'])
            new_content_view_version: str = c_update_response['input']['content_view_version_id']
            for env in environments:
                check_continue()
                promote_response: dict = make_request(
                    f'/katello/api/content_view_versions/{new_content_view_version}/promote', \
                    parametres={'environment_ids': [env]}, request_type='post')
                show_task_progress(promote_response['id'], action='promote')
            # delete obosolete composite content view versions
            check_continue()
            delete_content_view_versions(composite_view['id'], composite_view['name'])
        else:
            log(f"Failed to update the content view '{composite_view['name']}' " \
                f"(id:{composite_view['id']})!")
    log('All composite views updated, promoted and cleaned.')

    # delete obsolete noncomposite view version
    log('Cleaning obsolete noncomposite view versins')
    for d_noncomposite_view in noncomposite_views['results']:
        if d_noncomposite_view['label'] != 'Default_Organization_View':
            check_continue()
            delete_content_view_versions(d_noncomposite_view['id'],d_noncomposite_view['name'])
    log('Noncomposite views cleanup done.')

    check_continue()
    SESSION.close()
    log('Update done.')
    exit(0)
